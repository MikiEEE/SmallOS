"""Shared static types for smallOS.

Runtime modules import these definitions only while type checking so embedded
targets do not need to provide the :mod:`typing` module.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable, Mapping, Sequence
from typing import TYPE_CHECKING, Any, Literal, Protocol, TypeAlias, TypedDict, TypeVar

if TYPE_CHECKING:
    from .SmallOS import SmallOS


T = TypeVar("T")
SocketBuffer: TypeAlias = bytes | bytearray | memoryview
SocketOperation: TypeAlias = Literal["accept", "recv", "send", "handshake"]
SocketRetryMode: TypeAlias = Literal["read", "write"] | None


class TaskLike(Protocol):
    """Minimum task interface used by queues and scheduler integrations."""

    priority: int
    isWatcher: bool
    @property
    def done(self) -> bool: ...

    def getID(self) -> int: ...


class KernelLike(Protocol):
    """Platform operations consumed by the scheduler and output layer."""

    def write(self, msg: str) -> Any: ...
    def scheduler_now_ms(self) -> int: ...
    def sleep_ms(self, delay_ms: int) -> None: ...
    def supports_external_wait_objects(self) -> bool: ...
    def io_wait(
        self,
        readables: Iterable[Any],
        writables: Iterable[Any],
        timeout_ms: int | None = None,
    ) -> tuple[Sequence[Any], Sequence[Any]]: ...


class WakeupChannelLike(Protocol):
    """Opaque readiness channel used to wake a scheduler across threads."""

    @property
    def wait_object(self) -> Any: ...

    def notify(self) -> None: ...
    def drain(self) -> None: ...
    def close(self) -> None: ...


class WakeupKernelLike(Protocol):
    """Optional kernel boundary for cross-thread scheduler wakeups."""

    def supports_wakeup_channel(self) -> bool: ...
    def create_wakeup_channel(self) -> WakeupChannelLike: ...


class PassiveTCPKernelLike(Protocol):
    """Platform-neutral passive TCP operations used by server consumers."""

    def supports_tcp_server(self) -> bool: ...
    def supports_reuse_address(self) -> bool: ...
    def resolve_passive_address(self, host: str, port: int) -> Any: ...
    def socket_open(self, address_info: Any) -> Any: ...
    def socket_setblocking(self, sock: Any, flag: bool) -> None: ...
    def socket_set_reuse_address(self, sock: Any, enabled: bool) -> None: ...
    def socket_bind(self, sock: Any, address_info: Any) -> None: ...
    def socket_listen(self, sock: Any, backlog: int) -> None: ...
    def socket_accept(self, listener: Any) -> tuple[Any, Any]: ...
    def socket_local_address(self, sock: Any) -> Any: ...
    def socket_peer_address(self, sock: Any) -> Any | None: ...
    def socket_close(self, sock: Any) -> None: ...


class SocketKernelLike(Protocol):
    """Optional kernel boundary for operation-aware byte-stream I/O."""

    def socket_send(self, sock: Any, data: SocketBuffer) -> int: ...
    def socket_retry_mode(
        self, exc: BaseException, operation: SocketOperation
    ) -> SocketRetryMode: ...


class AdapterCompletionLike(Protocol):
    """Structural completion record consumed by the scheduler."""

    job_id: int
    value: Any
    exception: BaseException | None
    cancelled: bool

    @property
    def has_value(self) -> bool: ...


class ExecutionAdapterLike(Protocol):
    """Structural execution-adapter boundary consumed by ``SmallOS``."""

    @property
    def name(self) -> str: ...

    @property
    def wait_object(self) -> Any: ...

    @property
    def pending_count(self) -> int: ...

    @property
    def closed(self) -> bool: ...

    def _bind_runtime(self, runtime: SmallOS) -> None: ...

    def submit(
        self,
        job_id: int,
        callable_obj: Callable[..., Any],
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> None: ...

    def cancel(self, job_id: int) -> bool: ...

    def drain_completions(self) -> Iterable[AdapterCompletionLike]: ...


class RuntimeErrorEvent(TypedDict):
    task_id: int
    task_name: str
    parent_id: int | None
    exception: BaseException
    exception_type: str | None
    exception_repr: str
    is_cancelled: bool
    blocked_reason: str | None
    waiting_signal: int | None
    io_wait_mode: str | None
    join_target_id: int | None
    join_pending_ids: list[int]
    traceback_text: str | None
    adapter_name: str | None
    adapter_job_id: int | None


class SmallOSConfigData(TypedDict, total=False):
    task_capacity: int
    oslist_length: int
    priority_levels: int
    num_categories: int
    io_buffer_length: int
    eternal_watchers: bool
    client_defaults: Mapping[str, Mapping[str, int]]
    clients: Mapping[str, Mapping[str, int]]


class TerminalStatus(TypedDict):
    terminal_visible: bool
    buffered_messages: int
    buffer_length: int


TaskRoutine: TypeAlias = Callable[..., T | Awaitable[T]]
ErrorHandler: TypeAlias = Callable[[RuntimeErrorEvent], None]
TaskTarget: TypeAlias = int | TaskLike
