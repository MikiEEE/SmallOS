"""Shared execution-adapter instruction and completion contracts."""

from __future__ import annotations

try:
    from typing import TYPE_CHECKING as _type_checking
except ImportError:  # pragma: no cover - constrained runtimes
    _type_checking = False

if _type_checking:
    from collections.abc import Callable
    from types import TracebackType
    from typing import Any, TypeVar

    from ..SmallOS import SmallOS
    from ..awaitables import InstructionAwaitable

    _AdapterT = TypeVar("_AdapterT", bound="ExecutionAdapter")

from ..awaitables import adapter_call_instruction
from .errors import AdapterUnavailableError


_MISSING: object = object()


def _is_base_exception(value: object) -> bool:
    """Check dynamically supplied completion failures without trusting hints."""
    return isinstance(value, BaseException)


class AdapterCompletion:
    """One completed adapter job, represented by exactly one outcome."""

    def __init__(
        self,
        job_id: int,
        value: Any = _MISSING,
        exception: BaseException | None = None,
        cancelled: bool = False,
    ) -> None:
        if type(job_id) is not int:
            raise TypeError("AdapterCompletion job_id must be an integer.")
        if job_id <= 0:
            raise ValueError("AdapterCompletion job_id must be positive.")
        if exception is not None and not _is_base_exception(exception):
            raise TypeError(
                "AdapterCompletion exception must derive from BaseException."
            )
        if type(cancelled) is not bool:
            raise TypeError("AdapterCompletion cancelled must be a boolean.")
        outcome_count = int(value is not _MISSING) + int(exception is not None) + int(cancelled)
        if outcome_count != 1:
            raise ValueError("AdapterCompletion requires exactly one outcome.")
        self.job_id: int = job_id
        self.value: Any = value
        self.exception: BaseException | None = exception
        self.cancelled: bool = cancelled

    @property
    def has_value(self) -> bool:
        """Whether this completion carries a successful value, including ``None``."""
        return self.value is not _MISSING

    @classmethod
    def result(cls, job_id: int, value: Any) -> AdapterCompletion:
        """Build a successful completion."""
        return cls(job_id, value=value)

    @classmethod
    def failed(cls, job_id: int, exc: BaseException) -> AdapterCompletion:
        """Build a failed completion."""
        return cls(job_id, exception=exc)

    @classmethod
    def cancelled_result(cls, job_id: int) -> AdapterCompletion:
        """Build a foreign-runtime cancellation completion."""
        return cls(job_id, cancelled=True)


class ExecutionAdapter:
    """
    Base API for adapters that execute user callables outside SmallOS.

    Runtime integration is deliberately structural: subclasses provide the
    wait object and job lifecycle methods, while this class owns only the
    user-facing ``call()`` instruction and single-runtime binding rule.
    """

    def __init__(self, name: str) -> None:
        if not name:
            raise ValueError("adapter name must not be empty")
        self._adapter_name: str = str(name)
        self._runtime_binding: dict[str, SmallOS] = {}
        self._bound_runtime: SmallOS | None = None

    @property
    def name(self) -> str:
        """Stable adapter name used in diagnostics."""
        return self._adapter_name

    def call(
        self,
        callable_obj: Callable[..., Any],
        /,
        *args: Any,
        **kwargs: Any,
    ) -> InstructionAwaitable[Any]:
        """Build an untyped call instruction for custom adapter subclasses."""
        if not callable(callable_obj):
            raise TypeError("adapter call target must be callable")
        return adapter_call_instruction(self, callable_obj, args, kwargs)

    def _bind_runtime(self, runtime: SmallOS) -> None:
        """Bind one live adapter to exactly one SmallOS scheduler."""
        bound_runtime = self._runtime_binding.setdefault("runtime", runtime)
        if bound_runtime is not runtime:
            raise AdapterUnavailableError(
                "{} is already bound to another SmallOS runtime".format(self.name)
            )
        self._bound_runtime = bound_runtime

    @property
    def wait_object(self) -> Any:
        """Return the readable completion notification object."""
        raise NotImplementedError

    @property
    def pending_count(self) -> int:
        """Return the number of accepted jobs not yet completed."""
        raise NotImplementedError

    @property
    def closed(self) -> bool:
        """Whether shutdown has begun and new work must be rejected."""
        raise NotImplementedError

    def submit(
        self,
        job_id: int,
        callable_obj: Callable[..., Any],
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> None:
        """Submit a runtime-assigned job without blocking the scheduler."""
        raise NotImplementedError

    def cancel(self, job_id: int) -> bool:
        """Request best-effort cancellation of one job."""
        raise NotImplementedError

    def drain_completions(self) -> list[AdapterCompletion]:
        """Drain every currently queued completion."""
        raise NotImplementedError

    def shutdown(self, wait: bool = True, cancel_pending: bool = False) -> None:
        """Stop accepting work and release adapter-owned resources."""
        raise NotImplementedError

    def __enter__(self: _AdapterT) -> _AdapterT:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.shutdown(wait=True, cancel_pending=exc_type is not None)
