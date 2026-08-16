"""Dependency-free contracts and errors for optional execution adapters.

Desktop adapter implementations are intentionally not imported here. Import
``ThreadAdapter`` or ``AsyncioAdapter`` from their explicit modules so core and
MicroPython-oriented package imports do not load desktop concurrency modules.
"""

from .base import AdapterCompletion, ExecutionAdapter
from .errors import (
    AdapterCancelledError,
    AdapterCapacityError,
    AdapterClosedError,
    AdapterError,
    AdapterExecutionError,
    AdapterProtocolError,
    AdapterUnavailableError,
)

__all__ = [
    "AdapterCancelledError",
    "AdapterCapacityError",
    "AdapterClosedError",
    "AdapterCompletion",
    "AdapterError",
    "AdapterExecutionError",
    "AdapterProtocolError",
    "AdapterUnavailableError",
    "ExecutionAdapter",
]
