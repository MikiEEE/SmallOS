"""Dependency-free errors shared by SmallOS execution adapters."""

from __future__ import annotations

class AdapterError(Exception):
    """Base class for execution-adapter failures."""


class AdapterUnavailableError(AdapterError):
    """Raised when an adapter cannot run with the active runtime or kernel."""


class AdapterClosedError(AdapterError):
    """Raised when work is submitted after adapter shutdown has started."""


class AdapterCapacityError(AdapterError):
    """Raised when an adapter's bounded outstanding-work limit is full."""


class AdapterProtocolError(AdapterError):
    """Raised when an adapter violates the scheduler completion contract."""


class AdapterCancelledError(AdapterError):
    """Raised when the foreign runtime cancels an adapter operation."""


class AdapterExecutionError(AdapterError):
    """Wrap a foreign ``BaseException`` that SmallOS must not inject directly."""

    def __init__(self, message: str, original: BaseException | None = None) -> None:
        super().__init__(message)
        self.original = original


def normalize_adapter_exception(
    exc: BaseException,
    adapter_name: str = "adapter",
    cancelled: bool = False,
) -> Exception:
    """Return an exception safe to throw through ``SmallTask.execute()``."""
    if cancelled:
        return AdapterCancelledError(
            "{} operation was cancelled: {}".format(adapter_name, exc)
        )
    if isinstance(exc, Exception):
        return exc
    return AdapterExecutionError(
        "{} operation raised {}: {}".format(
            adapter_name,
            type(exc).__name__,
            exc,
        ),
        original=exc,
    )
