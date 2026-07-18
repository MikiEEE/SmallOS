"""
Awaitable helpers for the native smallOS runtime.

The scheduler does not attempt to understand arbitrary Python awaitables.
Instead, every smallOS primitive returns an object whose ``__await__`` method
emits a ``TaskInstruction``. ``SmallOS`` consumes those instructions and decides
when the task should run again.

This is the key separation of responsibilities in the runtime:
- tasks describe what they want to wait for
- the scheduler decides when that wait is satisfied
"""

from __future__ import annotations

try:
    from typing import TYPE_CHECKING
except ImportError:  # pragma: no cover - exercised on constrained runtimes
    TYPE_CHECKING = False

if TYPE_CHECKING:
    from collections.abc import Callable, Generator, Iterable
    from typing import Any, Generic, TypeVar

    from ._types import TaskTarget

    T = TypeVar("T")


class TaskInstruction:
    """
    Minimal message object passed from a coroutine to the scheduler.

    ``operation`` names the requested scheduler action and ``payload`` holds the
    values needed to carry it out. Keeping this object tiny makes the protocol
    easier to debug and more realistic to port to constrained runtimes.
    """

    def __init__(self, operation: str, **payload: Any) -> None:
        self.operation = operation
        self.payload = payload

    def __repr__(self) -> str:
        return "TaskInstruction(operation={!r}, payload={!r})".format(
            self.operation,
            self.payload,
        )


class InstructionAwaitable(Generic[T] if TYPE_CHECKING else object):
    """
    Tiny awaitable wrapper shared by the public helpers below.

    The wrapped instruction is yielded once. Later, when ``SmallOS`` resumes the
    blocked task, the value sent back in becomes the return value of the
    ``await`` expression in user code.
    """

    def __init__(self, instruction: TaskInstruction) -> None:
        self.instruction = instruction

    def __await__(self) -> Generator[TaskInstruction, Any, T]:
        """Yield one scheduler instruction and then return the resume value."""
        result = yield self.instruction
        return result


def sleep_instruction(seconds: float) -> InstructionAwaitable[None]:
    """Create the awaitable used for cooperative sleeping."""
    return InstructionAwaitable(TaskInstruction("sleep", seconds=seconds))


def wait_signal_instruction(signal: int) -> InstructionAwaitable[int]:
    """Create the awaitable used for waiting on a task signal."""
    return InstructionAwaitable(TaskInstruction("wait_signal", signal=signal))


def yield_now_instruction() -> InstructionAwaitable[None]:
    """Create the awaitable used for a voluntary scheduler yield."""
    return InstructionAwaitable(TaskInstruction("yield_now"))


def join_instruction(target: TaskTarget) -> InstructionAwaitable[Any]:
    """Create the awaitable used for waiting on a single task."""
    return InstructionAwaitable(TaskInstruction("join", target=target))


def join_all_instruction(targets: Iterable[TaskTarget]) -> InstructionAwaitable[list[Any]]:
    """Create the awaitable used for waiting on several tasks at once."""
    return InstructionAwaitable(TaskInstruction("join_all", targets=list(targets)))


def wait_readable_instruction(io_obj: Any) -> InstructionAwaitable[Any]:
    """Create the awaitable used for waiting until an I/O object is readable."""
    return InstructionAwaitable(TaskInstruction("wait_readable", io_obj=io_obj))


def wait_writable_instruction(io_obj: Any) -> InstructionAwaitable[Any]:
    """Create the awaitable used for waiting until an I/O object is writable."""
    return InstructionAwaitable(TaskInstruction("wait_writable", io_obj=io_obj))


def adapter_call_instruction(
    adapter: Any,
    callable_obj: Callable[..., T],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> InstructionAwaitable[T]:
    """Create an awaitable for one call through an execution adapter."""
    return InstructionAwaitable(
        TaskInstruction(
            "adapter_call",
            adapter=adapter,
            callable=callable_obj,
            args=args,
            kwargs=kwargs,
        )
    )
