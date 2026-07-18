"""Persistent-loop escape hatch for user-supplied asyncio libraries."""

from __future__ import annotations

import asyncio
import inspect
import threading
from typing import cast

try:
    from typing import TYPE_CHECKING as _type_checking
except ImportError:  # pragma: no cover - desktop-only module
    _type_checking = False

if _type_checking:
    from collections.abc import Awaitable, Callable
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
    AdapterUnavailableError,
    normalize_adapter_exception,
)


def _is_positive_int(value: object) -> bool:
    return type(value) is int and value > 0


class AsyncioAdapter(ExecutionAdapter):
    """Run async callable factories on one persistent asyncio loop thread."""

    def __init__(
        self,
        max_pending: int = 64,
        thread_name: str = "smallos-asyncio-adapter",
        startup_timeout: float = 5.0,
    ) -> None:
        if not _is_positive_int(max_pending):
            raise ValueError("max_pending must be a positive integer")
        if isinstance(startup_timeout, bool) or startup_timeout <= 0:
            raise ValueError("startup_timeout must be positive")
        super().__init__("asyncio")
        self._max_pending: int = max_pending
        self._channel: CompletionChannel = CompletionChannel()
        self._lock: threading.Lock = threading.Lock()
        self._ready: threading.Event = threading.Event()
        self._closed: bool = False
        self._loop: asyncio.AbstractEventLoop | None = None
        self._startup_error: BaseException | None = None
        self._accepted: set[int] = set()
        self._cancel_requested: set[int] = set()
        self._tasks: dict[int, asyncio.Future[Any]] = {}
        self._shutdown_task: asyncio.Task[None] | None = None
        self._shutdown_error: BaseException | None = None
        self._thread: threading.Thread = threading.Thread(
            target=self._run_loop,
            name=thread_name,
            daemon=False,
        )
        try:
            self._thread.start()
        except BaseException as exc:
            with self._lock:
                self._closed = True
            self._channel.close()
            raise AdapterUnavailableError(
                "AsyncioAdapter loop thread could not start: {}".format(exc)
            ) from exc
        if not self._ready.wait(startup_timeout):
            with self._lock:
                self._closed = True
            self._channel.close()
            raise AdapterUnavailableError(
                "AsyncioAdapter loop did not start within {} seconds".format(
                    startup_timeout
                )
            )
        if self._startup_error is not None:
            self._thread.join()
            raise AdapterUnavailableError(
                "AsyncioAdapter loop failed to start: {}".format(self._startup_error)
            )

    def call(
        self,
        callable_obj: Callable[..., Awaitable[_ResultT]],
        /,
        *args: Any,
        **kwargs: Any,
    ) -> InstructionAwaitable[_ResultT]:
        """Return an awaitable for the async callable's eventual result type."""
        if not callable(callable_obj):
            raise TypeError("adapter call target must be callable")
        instruction = adapter_call_instruction(self, callable_obj, args, kwargs)
        return cast("InstructionAwaitable[_ResultT]", instruction)

    @property
    def wait_object(self) -> socket.socket:
        return self._channel.wait_object

    @property
    def pending_count(self) -> int:
        with self._lock:
            return len(self._accepted)

    @property
    def closed(self) -> bool:
        with self._lock:
            return self._closed

    @property
    def shutdown_error(self) -> BaseException | None:
        """Return an unexpected loop or teardown failure, if one occurred."""
        with self._lock:
            return self._shutdown_error

    def _run_loop(self) -> None:
        loop: asyncio.AbstractEventLoop | None = None
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            with self._lock:
                self._loop = loop
                should_run = not self._closed
            self._ready.set()
            if should_run:
                loop.run_forever()
                with self._lock:
                    if not self._closed and self._shutdown_error is None:
                        self._shutdown_error = AdapterUnavailableError(
                            "AsyncioAdapter loop stopped unexpectedly"
                        )
                        self._closed = True
        except BaseException as exc:
            with self._lock:
                if not self._ready.is_set():
                    self._startup_error = exc
                elif self._shutdown_error is None:
                    self._shutdown_error = exc
                self._closed = True
            self._ready.set()
        finally:
            if loop is not None:
                try:
                    asyncio.set_event_loop(None)
                except BaseException as exc:
                    with self._lock:
                        if self._shutdown_error is None:
                            self._shutdown_error = exc
                try:
                    loop.close()
                except BaseException as exc:
                    with self._lock:
                        if self._shutdown_error is None:
                            self._shutdown_error = exc
            self._channel.close()

    def submit(
        self,
        job_id: int,
        callable_obj: Callable[..., Any],
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> None:
        if not callable(callable_obj):
            raise TypeError("AsyncioAdapter target must be callable")

        with self._lock:
            if self._closed:
                raise AdapterClosedError("AsyncioAdapter is closed")
            if len(self._accepted) >= self._max_pending:
                raise AdapterCapacityError(
                    "AsyncioAdapter reached max_pending ({})".format(
                        self._max_pending
                    )
                )
            loop = self._loop
            self._accepted.add(job_id)
            if loop is None or not loop.is_running():
                self._accepted.discard(job_id)
                raise AdapterUnavailableError("AsyncioAdapter loop is not running")
            try:
                # Queue the start callback while holding the lifecycle lock so
                # shutdown cannot overtake an accepted submission.
                loop.call_soon_threadsafe(
                    self._start_job,
                    job_id,
                    callable_obj,
                    args,
                    kwargs,
                )
            except BaseException:
                self._accepted.discard(job_id)
                raise

    def _start_job(
        self,
        job_id: int,
        callable_obj: Callable[..., Any],
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> None:
        with self._lock:
            if job_id not in self._accepted:
                return
            cancel_requested = job_id in self._cancel_requested

        if cancel_requested:
            self._finish_job(job_id, AdapterCompletion.cancelled_result(job_id))
            return

        try:
            awaitable = callable_obj(*args, **kwargs)
        except BaseException as exc:
            self._finish_job(
                job_id,
                AdapterCompletion.failed(
                    job_id,
                    normalize_adapter_exception(exc, self.name),
                ),
            )
            return

        if not inspect.isawaitable(awaitable):
            self._finish_job(
                job_id,
                AdapterCompletion.failed(
                    job_id,
                    AdapterProtocolError(
                        "AsyncioAdapter callable returned a non-awaitable value"
                    ),
                ),
            )
            return

        try:
            loop = asyncio.get_running_loop()
            if asyncio.isfuture(awaitable):
                get_loop = getattr(awaitable, "get_loop", None)
                if callable(get_loop) and get_loop() is not loop:
                    raise AdapterProtocolError(
                        "AsyncioAdapter cannot accept a Future or Task "
                        "owned by another event loop"
                    )
            task = asyncio.ensure_future(awaitable, loop=loop)
        except BaseException as exc:
            close = getattr(awaitable, "close", None)
            if callable(close):
                close()
            self._finish_job(
                job_id,
                AdapterCompletion.failed(
                    job_id,
                    normalize_adapter_exception(exc, self.name),
                ),
            )
            return

        self._tasks[job_id] = task
        task.add_done_callback(
            lambda completed, completed_job_id=job_id: self._on_task_done(
                completed_job_id,
                completed,
            )
        )

    def _on_task_done(self, job_id: int, task: asyncio.Future[Any]) -> None:
        self._tasks.pop(job_id, None)
        if task.cancelled():
            completion = AdapterCompletion.cancelled_result(job_id)
        else:
            try:
                value = task.result()
            except BaseException as exc:
                completion = AdapterCompletion.failed(
                    job_id,
                    normalize_adapter_exception(exc, self.name),
                )
            else:
                completion = AdapterCompletion.result(job_id, value)
        self._finish_job(job_id, completion)

    def _finish_job(self, job_id: int, completion: AdapterCompletion) -> None:
        with self._lock:
            self._accepted.discard(job_id)
            self._cancel_requested.discard(job_id)
        self._channel.post(completion)

    def cancel(self, job_id: int) -> bool:
        with self._lock:
            if job_id not in self._accepted:
                return False
            self._cancel_requested.add(job_id)
            loop = self._loop
            if loop is None or not loop.is_running():
                return False
            try:
                loop.call_soon_threadsafe(self._cancel_on_loop, job_id)
            except (RuntimeError, OSError):
                return False
            return True

    def _cancel_on_loop(self, job_id: int) -> None:
        task = self._tasks.get(job_id)
        if task is not None:
            task.cancel()

    def drain_completions(self) -> list[AdapterCompletion]:
        return self._channel.drain()

    async def _shutdown_async(self, cancel_pending: bool) -> None:
        loop = asyncio.get_running_loop()
        try:
            tasks = list(self._tasks.values())
            if cancel_pending:
                for task in tasks:
                    task.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            await loop.shutdown_asyncgens()
            shutdown_default_executor = getattr(
                loop,
                "shutdown_default_executor",
                None,
            )
            if shutdown_default_executor is not None:
                await shutdown_default_executor()
        except BaseException as exc:
            # Preserve cleanup progress and avoid leaving a non-daemon loop
            # thread alive if a library-owned shutdown hook fails.
            with self._lock:
                self._shutdown_error = exc
        finally:
            loop.call_soon(loop.stop)

    def _begin_shutdown(self, cancel_pending: bool) -> None:
        if self._shutdown_task is not None:
            return
        self._shutdown_task = asyncio.create_task(
            self._shutdown_async(cancel_pending)
        )

    def shutdown(self, wait: bool = True, cancel_pending: bool = False) -> None:
        with self._lock:
            if self._closed:
                if wait and self._thread.is_alive():
                    thread = self._thread
                else:
                    return
            else:
                self._closed = True
                thread = self._thread
            loop = self._loop
            if loop is not None and loop.is_running():
                try:
                    # Every accepted submit callback was queued under this same
                    # lock, so shutdown is ordered after those submissions.
                    loop.call_soon_threadsafe(self._begin_shutdown, cancel_pending)
                except (RuntimeError, OSError):
                    pass
        if wait and thread is not threading.current_thread():
            thread.join()
