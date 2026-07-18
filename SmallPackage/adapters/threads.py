"""Thread-backed escape hatch for user-supplied blocking callables."""

from __future__ import annotations

import concurrent.futures
import inspect
import threading

try:
    from typing import TYPE_CHECKING as _type_checking
except ImportError:  # pragma: no cover - desktop-only module
    _type_checking = False

if _type_checking:
    from collections.abc import Callable
    import socket
    from typing import Any, TypeVar

    from ..awaitables import InstructionAwaitable

    _ResultT = TypeVar("_ResultT")

from ..awaitables import adapter_call_instruction
from ._completion import CompletionChannel
from .base import AdapterCompletion, ExecutionAdapter
from .errors import (
    AdapterCapacityError,
    AdapterClosedError,
    AdapterProtocolError,
    normalize_adapter_exception,
)


def _is_positive_int(value: object) -> bool:
    return type(value) is int and value > 0


class ThreadAdapter(ExecutionAdapter):
    """Execute synchronous user callables in a bounded desktop thread pool."""

    def __init__(
        self,
        max_workers: int | None = None,
        max_pending: int = 64,
        thread_name_prefix: str = "smallos-adapter",
    ) -> None:
        if max_workers is not None and not _is_positive_int(max_workers):
            raise ValueError("max_workers must be a positive integer or None")
        if not _is_positive_int(max_pending):
            raise ValueError("max_pending must be a positive integer")
        super().__init__("threads")
        self._max_pending: int = max_pending
        self._channel: CompletionChannel = CompletionChannel()
        self._lock: threading.Lock = threading.Lock()
        self._closed: bool = False
        self._futures: dict[int, concurrent.futures.Future[Any]] = {}
        self._reserved: int = 0
        try:
            self._executor = concurrent.futures.ThreadPoolExecutor(
                max_workers=max_workers,
                thread_name_prefix=thread_name_prefix,
            )
        except BaseException:
            self._channel.close()
            raise

    def call(
        self,
        callable_obj: Callable[..., _ResultT],
        /,
        *args: Any,
        **kwargs: Any,
    ) -> InstructionAwaitable[_ResultT]:
        """Return an awaitable whose type matches the blocking callable result."""
        if not callable(callable_obj):
            raise TypeError("adapter call target must be callable")
        return adapter_call_instruction(self, callable_obj, args, kwargs)

    @property
    def wait_object(self) -> socket.socket:
        return self._channel.wait_object

    @property
    def pending_count(self) -> int:
        with self._lock:
            return self._reserved

    @property
    def closed(self) -> bool:
        with self._lock:
            return self._closed

    def submit(
        self,
        job_id: int,
        callable_obj: Callable[..., Any],
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> None:
        if not callable(callable_obj):
            raise TypeError("ThreadAdapter target must be callable")

        with self._lock:
            if self._closed:
                raise AdapterClosedError("ThreadAdapter is closed")
            if self._reserved >= self._max_pending:
                raise AdapterCapacityError(
                    "ThreadAdapter reached max_pending ({})".format(self._max_pending)
                )
            self._reserved += 1

        try:
            future = self._executor.submit(callable_obj, *args, **kwargs)
        except BaseException:
            with self._lock:
                self._reserved -= 1
            raise

        with self._lock:
            self._futures[job_id] = future
        future.add_done_callback(
            lambda completed, completed_job_id=job_id: self._on_done(
                completed_job_id,
                completed,
            )
        )

    def _on_done(
        self,
        job_id: int,
        future: concurrent.futures.Future[Any],
    ) -> None:
        with self._lock:
            self._futures.pop(job_id, None)
            if self._reserved > 0:
                self._reserved -= 1

        if future.cancelled():
            completion = AdapterCompletion.cancelled_result(job_id)
        else:
            try:
                value = future.result()
            except BaseException as exc:
                completion = AdapterCompletion.failed(
                    job_id,
                    normalize_adapter_exception(exc, self.name),
                )
            else:
                if inspect.isawaitable(value):
                    close = getattr(value, "close", None)
                    if callable(close):
                        close()
                    completion = AdapterCompletion.failed(
                        job_id,
                        AdapterProtocolError(
                            "ThreadAdapter callable returned an awaitable; "
                            "use AsyncioAdapter for async callables"
                        ),
                    )
                else:
                    completion = AdapterCompletion.result(job_id, value)
        self._channel.post(completion)
        with self._lock:
            close_after_completion = self._closed and self._reserved == 0
        if close_after_completion:
            self._channel.close()

    def cancel(self, job_id: int) -> bool:
        with self._lock:
            future = self._futures.get(job_id)
        if future is None:
            return False
        return bool(future.cancel())

    def drain_completions(self) -> list[AdapterCompletion]:
        return self._channel.drain()

    def shutdown(self, wait: bool = True, cancel_pending: bool = False) -> None:
        with self._lock:
            was_closed = self._closed
            self._closed = True
            if was_closed and not wait:
                return

        self._executor.shutdown(wait=wait, cancel_futures=cancel_pending)
        if wait:
            self._channel.close()
            return

        # Running callbacks may still need to publish. Close the channel after
        # the final one instead of racing them here.
        with self._lock:
            should_close = self._reserved == 0
        if should_close:
            self._channel.close()
