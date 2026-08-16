"""
Native smallOS scheduler.

This module is the core of the async runtime. Tasks yield ``TaskInstruction``
objects, the scheduler interprets them, and tasks are resumed according to
smallOS priority rules rather than ``asyncio``'s event loop behavior.

That separation is what makes the project-specific features possible:
- custom priorities
- explicit signal integration
- a runtime shape that is easier to port to MicroPython
"""

from __future__ import annotations

try:
    from typing import TYPE_CHECKING
except ImportError:  # pragma: no cover
    TYPE_CHECKING = False

if TYPE_CHECKING:
    from collections.abc import Iterable
    from typing import Any

    from .Kernel import Kernel
    from .SmallTask import SmallTask
    from ._types import (
        ErrorHandler,
        ExecutionAdapterLike,
        RuntimeErrorEvent,
        SmallOSConfigData,
    )

from .awaitables import TaskInstruction
from .SmallIO import SmallIO
from .SmallConfig import SmallOSConfig
from .OSlist import OSList
from .SmallErrors import MaxProcessError, TaskCancelledError, UnsupportedAwaitableError
from .adapters.errors import (
    AdapterCancelledError,
    AdapterClosedError,
    AdapterProtocolError,
    AdapterUnavailableError,
    normalize_adapter_exception,
)


_MISSING = object()


class SmallOS(SmallIO):
    """
    Cooperative event loop for ``SmallTask`` coroutines.

    The scheduler deliberately stays narrow in scope: pick a runnable task,
    advance it once, interpret the yielded instruction, and update queues.
    Keeping that control flow explicit makes the runtime easier to understand
    and easier to customize.
    """

    def __init__(
        self,
        size: int | None = None,
        config: SmallOSConfig | SmallOSConfigData | None = None,
        **kwargs: Any,
    ) -> None:
        """
        Create the runtime shell plus its task and shell registries.

        ``config`` may be a ``SmallOSConfig`` instance or a plain dict. Older
        constructor-style overrides such as ``size`` still work and take
        precedence over the loaded config values when both are supplied.
        """
        config_overrides = {}
        if size is not None:
            config_overrides["task_capacity"] = size
        if "priority_levels" in kwargs:
            config_overrides["priority_levels"] = kwargs.pop("priority_levels")
        if "io_buffer_length" in kwargs:
            config_overrides["io_buffer_length"] = kwargs.pop("io_buffer_length")
        if "eternal_watchers" in kwargs:
            config_overrides["eternal_watchers"] = kwargs.pop("eternal_watchers")

        self.config = SmallOSConfig.from_dict(config)
        if config_overrides:
            self.config = self.config.copy(**config_overrides)

        self.sleepTasks = []
        self.waitingTasks = []
        self.wakeUpdate = []
        self.ioReadWaiters = {}
        self.ioWriteWaiters = {}
        self._io_wait_set = None
        self._adapter_jobs: dict[
            int,
            tuple[ExecutionAdapterLike, SmallTask[Any]],
        ] = {}
        self._next_adapter_job_id = 0
        self.shells = []
        self.tasks = OSList(self.config.priority_levels, self.config.task_capacity)
        self.kernel = None
        self.eternalWatchers = self.config.eternal_watchers
        self.cursor = None
        self.errorHandler = None
        self.errorHandlerIncludeCancelled = False

        SmallIO.__init__(self, self.config.io_buffer_length)
        if kwargs:
            if kwargs.get("tasks", False):
                self.fork(kwargs["tasks"])
            if kwargs.get("shells", False):
                shells = kwargs["shells"]
                if isinstance(shells, list):
                    [shell.setOS(self) for shell in shells]
                    self.shells.extend(shells)
                else:
                    shells.setOS(self)
                    self.shells.append(shells)

    def startOS(self) -> None:
        """Compatibility entrypoint kept from the earlier project API."""
        return self.start()

    def start(self) -> None:
        """
        Run the scheduler until no live tasks remain.

        Each pass wakes expired sleepers, selects the highest-priority runnable
        task, advances it once, and then either finalizes it or handles the wait
        condition it requested.
        """
        self._open_io_wait_set()
        try:
            while len(self.tasks) != 0:
                self._wake_sleeping_tasks()
                if self.tasks.has_ready():
                    # Include newly ready I/O tasks in the priority decision.
                    self._wake_io_tasks(timeout_ms=0)
                else:
                    # Go directly to the blocking wait instead of first issuing
                    # a redundant zero-time poll.
                    if not self._idle_until_next_task():
                        break
                    self._wake_sleeping_tasks()

                self.cursor = self.tasks.pop()
                if self.cursor is None:
                    continue

                yielded = self.cursor.execute()
                if self.cursor.done:
                    # Finished tasks are finalized immediately so PID lookup and join
                    # bookkeeping always see a consistent terminal state.
                    self._finalize_task(self.cursor)
                else:
                    # Adapter failure diagnostics only describe the coroutine step
                    # resumed by that adapter. Once the step yields successfully,
                    # a later failure should not be attributed to the old job.
                    self._clear_adapter_resume_origin(self.cursor)
                    self._handle_yield(self.cursor, yielded)

                if not self.eternalWatchers and len(self.tasks) != 0 and self.tasks.isOnlyWatchers():
                    return
            return
        finally:
            self._close_io_wait_set()

    def _open_io_wait_set(self):
        """Create and seed the kernel's optional persistent readiness set."""
        self._close_io_wait_set()
        if self.kernel is None:
            return
        factory = getattr(self.kernel, "create_io_wait_set", None)
        if factory is None:
            return
        wait_set = factory()
        if wait_set is None:
            return

        self._io_wait_set = wait_set
        try:
            self._fail_invalid_io_waiters()
            for io_obj in self.ioReadWaiters:
                self._refresh_io_interest(io_obj)
            for io_obj in self.ioWriteWaiters:
                if io_obj not in self.ioReadWaiters:
                    self._refresh_io_interest(io_obj)
            for io_obj in self._collect_adapter_sources():
                self._refresh_io_interest(io_obj)
        except BaseException:
            self._close_io_wait_set()
            raise

    def _close_io_wait_set(self):
        """Close only the backend wait set, never the registered user objects."""
        wait_set = self._io_wait_set
        self._io_wait_set = None
        if wait_set is not None:
            wait_set.close()

    def next(self) -> SmallTask | None:
        """Return the next runnable task without advancing the main loop."""
        self.cursor = self.tasks.pop()
        return self.cursor

    def fork(
        self,
        children: SmallTask[Any] | list[SmallTask[Any]],
    ) -> int | list[int]:
        """Register one task or a list of tasks with the runtime."""
        if isinstance(children, list):
            ids = []
            for item in children:
                ids.append(self._fork_one(item))
            return ids
        return self._fork_one(children)

    def _fork_one(self, task: SmallTask[Any]) -> int:
        """Assign a PID, attach the runtime, and enqueue the task if runnable."""
        pid = self.tasks.insert(task)
        if pid == -1:
            raise MaxProcessError("All available PIDS are in use, cannot add more tasks.")

        task.setOS(self)
        if task.getExeStatus():
            self.tasks.enqueue(task)
        return pid

    def setKernel(self, kernel: Kernel) -> SmallOS:
        """Attach the platform abstraction used for time and output."""
        self.kernel = kernel
        return self

    def setEternalWatchers(self, isEternalWatcherPresent: bool) -> SmallOS:
        """Control whether the runtime exits once only watcher tasks remain."""
        self.eternalWatchers = isEternalWatcherPresent
        return self

    def setErrorHandler(
        self, handler: ErrorHandler | None, include_cancelled: bool = False
    ) -> SmallOS:
        """
        Install a best-effort runtime error observer for failed tasks.

        ``handler`` is a synchronous callable that receives one failure-event
        dictionary after the task has been finalized. Returning ``None`` removes
        the current handler.
        """
        if handler is not None and not callable(handler):
            raise TypeError("error handler must be callable or None.")
        self.errorHandler = handler
        self.errorHandlerIncludeCancelled = bool(include_cancelled)
        return self

    def _wake_sleeping_tasks(self):
        """Promote every expired sleeping task back onto the ready queues."""
        if not self.kernel:
            return

        for task in self.tasks.wake_sleeping(self.kernel.scheduler_now_ms()):
            self.resume_task(task)

    def _idle_until_next_task(self):
        """
        Sleep the host kernel until the next known wake-up time.

        This avoids busy-looping when every live task is blocked on time rather
        than CPU. If no kernel or future wake time exists, there is nothing
        useful to wait for and the scheduler should stop.
        """
        if not self.kernel:
            return False

        next_wake = self.tasks.next_wake_time()
        timeout = None
        if next_wake is not None:
            timeout = max(0, next_wake - self.kernel.scheduler_now_ms())

        has_wait_sources = bool(
            self.ioReadWaiters or self.ioWriteWaiters or self._adapter_jobs
        )
        if next_wake is None and not has_wait_sources:
            return False

        if has_wait_sources and hasattr(self.kernel, "io_wait"):
            self._wake_io_tasks(timeout_ms=timeout)
        elif timeout is not None and timeout > 0 and hasattr(self.kernel, "sleep_ms"):
            self.kernel.sleep_ms(timeout)
        return True

    def resume_task(
        self,
        task: SmallTask,
        value: Any = _MISSING,
        exc: BaseException | None = None,
        front: bool = False,
    ) -> int:
        """
        Requeue a blocked task with the value or exception that completed it.

        Centralizing resume logic here ensures scheduler-owned wait state is
        cleared before a task gets a chance to block on something else.
        """
        if task is None or task == -1 or task.done:
            return -1
        if self.tasks.search(task.getID()) == -1:
            return -1

        self._clear_wait_state(task)
        task.resume(value=value, exc=exc)
        self.tasks.enqueue(task, front=front)
        return 0

    def on_signal(self, task: SmallTask, sig: int) -> None:
        """Wake a task immediately if it is actively waiting on ``sig``."""
        if task._blocked_reason == "signal" and task._waiting_signal == sig:
            task.signals[sig] = 0
            self.resume_task(task, value=sig, front=True)

    def _handle_yield(self, task: SmallTask, yielded: Any) -> None:
        """
        Interpret one scheduler instruction emitted by a task.

        This method is the policy hub of the runtime. Every supported ``await``
        ends up in one branch here, which makes task state transitions explicit.
        """
        if yielded is None:
            # Treat bare ``None`` as an immediate cooperative yield so the task
            # remains runnable instead of getting stranded.
            self.resume_task(task)
            return

        if not isinstance(yielded, TaskInstruction):
            task.fail(
                UnsupportedAwaitableError(
                    "Task {!r} yielded unsupported awaitable {!r}".format(task.name, yielded)
                )
            )
            self._finalize_task(task)
            return

        operation = yielded.operation
        payload = yielded.payload

        if operation == "yield_now":
            # Voluntary CPU handoff: keep the task runnable at the same
            # priority, but let other tasks get a turn first.
            self.resume_task(task)
            return

        if operation == "sleep":
            seconds = payload.get("seconds", 0)
            if seconds < 0:
                task.fail(ValueError("sleep duration must be non-negative"))
                self._finalize_task(task)
                return

            delay_ms = max(0, int(seconds * 1000))
            wake_time = self.kernel.scheduler_now_ms() + delay_ms if self.kernel else delay_ms
            self._enter_sleep_wait(task, wake_time)
            return

        if operation == "wait_signal":
            signal = payload["signal"]
            if task.checkSignal(signal):
                self.resume_task(task, value=signal, front=True)
            else:
                self._enter_signal_wait(task, signal)
            return

        if operation == "wait_readable":
            self._enter_io_wait(task, payload["io_obj"], "read")
            return

        if operation == "wait_writable":
            self._enter_io_wait(task, payload["io_obj"], "write")
            return

        if operation == "adapter_call":
            self._handle_adapter_call(task, payload)
            return

        if operation == "join":
            target = self._resolve_task(payload["target"])
            if target is None:
                task.fail(LookupError("join target does not exist"))
                self._finalize_task(task)
                return

            if target.done:
                self._resume_from_completed(task, target)
            else:
                self._enter_join_wait(task, target)
            return

        if operation == "join_all":
            targets = self._normalize_targets(payload["targets"])
            if targets is None:
                task.fail(LookupError("join_all target does not exist"))
                self._finalize_task(task)
                return

            if not targets:
                self.resume_task(task, value=[], front=True)
                return

            first_exception = self._first_exception(targets)
            if first_exception is not None:
                self.resume_task(task, exc=first_exception, front=True)
                return

            pending = {child.getID() for child in targets if not child.done}
            if not pending:
                self.resume_task(task, value=[child.result for child in targets], front=True)
                return

            # Preserve the original child ordering for the eventual results
            # while also tracking a fast set of outstanding child PIDs.
            self._enter_join_all_wait(task, targets, pending)
            return

        task.fail(UnsupportedAwaitableError("Unknown instruction {!r}".format(operation)))
        self._finalize_task(task)

    def _adapter_name(self, adapter: object) -> str:
        """Return a stable best-effort name for adapter diagnostics."""
        try:
            name = getattr(adapter, "name", None)
        except BaseException:
            name = None
        if isinstance(name, str) and name:
            return name
        return type(adapter).__name__

    def _safe_adapter_exception(
        self,
        adapter: object,
        exc: object,
        cancelled: bool = False,
    ) -> Exception:
        """Normalize foreign exceptions before they enter a SmallTask."""
        if not isinstance(exc, BaseException):
            exc = AdapterProtocolError(
                "{} produced a non-exception failure value".format(
                    self._adapter_name(adapter)
                )
            )
        return normalize_adapter_exception(
            exc,
            self._adapter_name(adapter),
            cancelled=cancelled,
        )

    def _validate_adapter(self, adapter: Any) -> ExecutionAdapterLike:
        """Validate and bind the structural adapter contract on submission."""
        if self.kernel is None or not hasattr(self.kernel, "io_wait"):
            raise AdapterUnavailableError(
                "execution adapters require a kernel with io_wait()"
            )
        supports_external_waits = getattr(
            self.kernel,
            "supports_external_wait_objects",
            None,
        )
        if callable(supports_external_waits) and not supports_external_waits():
            raise AdapterUnavailableError(
                "{} cannot wait on adapter completion objects".format(
                    type(self.kernel).__name__
                )
            )

        for method_name in (
            "_bind_runtime",
            "submit",
            "cancel",
            "drain_completions",
        ):
            if not callable(getattr(adapter, method_name, None)):
                raise AdapterProtocolError(
                    "adapter is missing callable {}()".format(method_name)
                )

        try:
            is_closed = adapter.closed
        except BaseException as exc:
            raise AdapterProtocolError(
                "{} closed-state check failed: {}".format(
                    self._adapter_name(adapter),
                    exc,
                )
            ) from exc
        if type(is_closed) is not bool:
            raise AdapterProtocolError(
                "{} closed state must be boolean".format(
                    self._adapter_name(adapter)
                )
            )
        if is_closed:
            raise AdapterClosedError(
                "{} is closed".format(self._adapter_name(adapter))
            )

        adapter._bind_runtime(self)
        try:
            wait_object = adapter.wait_object
            hash(wait_object)
        except BaseException as exc:
            raise AdapterProtocolError(
                "{} has no usable completion wait object: {}".format(
                    self._adapter_name(adapter),
                    exc,
                )
            ) from exc

        validator = getattr(self.kernel, "validate_io_wait_object", None)
        if validator is not None:
            try:
                is_valid, exc = validator(wait_object)
            except BaseException as exc:
                raise AdapterUnavailableError(
                    "{} could not validate the completion wait object: {}".format(
                        type(self.kernel).__name__,
                        exc,
                    )
                ) from exc
            if not is_valid:
                raise AdapterUnavailableError(
                    "{} completion wait object is invalid: {}".format(
                        self._adapter_name(adapter),
                        exc,
                    )
                )
        return adapter

    def _handle_adapter_call(
        self,
        task: SmallTask[Any],
        payload: dict[str, Any],
    ) -> None:
        """Submit one foreign call and block ``task`` for its completion."""
        adapter_candidate = payload.get("adapter")
        callable_obj = payload.get("callable")
        args = payload.get("args", ())
        kwargs = payload.get("kwargs", {})

        try:
            adapter = self._validate_adapter(adapter_candidate)
            if not callable(callable_obj):
                raise TypeError("adapter call target must be callable")
            if not isinstance(args, tuple):
                raise AdapterProtocolError("adapter call args must be a tuple")
            if not isinstance(kwargs, dict):
                raise AdapterProtocolError("adapter call kwargs must be a dict")
        except BaseException as exc:
            safe_exc = self._safe_adapter_exception(adapter_candidate, exc)
            self.resume_task(task, exc=safe_exc, front=True)
            return

        self._next_adapter_job_id += 1
        job_id = self._next_adapter_job_id
        self._enter_adapter_wait(task, adapter, job_id)

        try:
            adapter.submit(job_id, callable_obj, args, kwargs)
        except BaseException as exc:
            self._adapter_jobs.pop(job_id, None)
            safe_exc = self._safe_adapter_exception(adapter, exc)
            self._record_adapter_resume_origin(task, adapter, job_id)
            self.resume_task(task, exc=safe_exc, front=True)

    def _record_adapter_resume_origin(
        self,
        task: SmallTask[Any],
        adapter: ExecutionAdapterLike,
        job_id: int,
    ) -> None:
        """Preserve adapter identity until the resumed coroutine step finishes."""
        task._adapter_resume_name = self._adapter_name(adapter)
        task._adapter_resume_job_id = job_id

    def _clear_adapter_resume_origin(self, task: SmallTask[Any]) -> None:
        """Clear diagnostics associated with a completed resume step."""
        task._adapter_resume_name = None
        task._adapter_resume_job_id = None

    def _resolve_task(self, target: int | SmallTask) -> SmallTask | None:
        """Normalize either a task object or a PID to a task object."""
        if not isinstance(target, int):
            return target
        found = self.tasks.search(target)
        return None if found == -1 else found

    def _normalize_targets(self, targets: Iterable[int | SmallTask]) -> list[SmallTask] | None:
        """Resolve a join target list while preserving caller-specified order."""
        normalized = []
        seen = set()
        for target in targets:
            task = self._resolve_task(target)
            if task is None or task == -1:
                return None
            if task.getID() in seen:
                continue
            seen.add(task.getID())
            normalized.append(task)
        return normalized

    def _resume_from_completed(self, waiter, target):
        """Resume a join waiter with either the child result or its exception."""
        if target.exception is not None:
            self.resume_task(waiter, exc=target.exception, front=True)
        else:
            self.resume_task(waiter, value=target.result, front=True)

    def _first_exception(self, tasks):
        """Return the first terminal exception in a task list, if any."""
        for task in tasks:
            if task.exception is not None:
                return task.exception
        return None

    def _clear_wait_state(self, task):
        """
        Remove a task from scheduler wait bookkeeping and reset its wait metadata.

        The scheduler owns the blocked-state lifecycle, so runtime transitions
        clear both registration-based wait structures and the task's stored wait
        markers from one place.
        """
        self._clear_wait_registration(task)
        self._clear_wait_metadata(task)

    def _clear_wait_metadata(self, task):
        """Reset the scheduler-owned wait metadata stored on ``task``."""
        task._blocked_reason = None
        task._wake_at = None
        task._waiting_signal = None
        task._join_target = None
        task._join_targets = None
        task._join_pending = set()
        task._io_wait_obj = None
        task._io_wait_mode = None
        task._adapter = None
        task._adapter_job_id = None

    def _begin_wait(self, task, reason):
        """Prepare a runnable task to transition into one blocked wait state."""
        self._clear_wait_state(task)
        task.block(reason)

    def _enter_sleep_wait(self, task, wake_time):
        """Put ``task`` to sleep until ``wake_time``."""
        self._begin_wait(task, "sleep")
        task._wake_at = wake_time
        self.tasks.add_sleeping(task, wake_time)

    def _enter_signal_wait(self, task, signal):
        """Block ``task`` until ``signal`` is delivered."""
        self._begin_wait(task, "signal")
        task._waiting_signal = signal

    def _enter_io_wait(self, task, io_obj, mode):
        """Register ``task`` for readable or writable I/O readiness."""
        reason = "wait_readable" if mode == "read" else "wait_writable"
        self._begin_wait(task, reason)
        task._io_wait_obj = io_obj
        task._io_wait_mode = mode
        validator = getattr(self.kernel, "validate_io_wait_object", None)
        if validator is not None:
            is_valid, exc = validator(io_obj)
            if not is_valid:
                self.resume_task(task, exc=self._clone_wait_error(exc), front=True)
                return
        try:
            self._register_io_wait(task, io_obj, mode)
        except Exception as exc:
            # Registration failures belong at the await expression; they should
            # not tear down the entire scheduler loop.
            self.resume_task(task, exc=exc, front=True)

    def _enter_adapter_wait(
        self,
        task: SmallTask[Any],
        adapter: ExecutionAdapterLike,
        job_id: int,
    ) -> None:
        """Block ``task`` on one adapter-owned external operation."""
        self._begin_wait(task, "adapter")
        task._adapter = adapter
        task._adapter_job_id = job_id
        self._adapter_jobs[job_id] = (adapter, task)

    def _enter_join_wait(self, task, target):
        """Block ``task`` until ``target`` finishes."""
        self._begin_wait(task, "join")
        task._join_target = target
        target.add_join_waiter(task)

    def _enter_join_all_wait(self, task, targets, pending):
        """Block ``task`` until every child in ``pending`` has completed."""
        self._begin_wait(task, "join_all")
        task._join_targets = list(targets)
        task._join_pending = set(pending)
        for child in targets:
            if not child.done:
                child.add_join_waiter(task)

    def _register_io_wait(self, task, io_obj, mode):
        """Register a task as waiting on an I/O object's readiness event."""
        waiters = self.ioReadWaiters if mode == "read" else self.ioWriteWaiters
        added_interest = io_obj not in waiters
        if io_obj not in waiters:
            waiters[io_obj] = []
        if task not in waiters[io_obj]:
            waiters[io_obj].append(task)
        if added_interest:
            try:
                self._refresh_io_interest(io_obj)
            except Exception:
                waiters[io_obj].remove(task)
                if not waiters[io_obj]:
                    del waiters[io_obj]
                raise

    def _refresh_io_interest(self, io_obj):
        """Apply one object's combined logical interest to a persistent wait set."""
        if self._io_wait_set is None:
            return
        adapter_readable = False
        for adapter, _task in self._adapter_jobs.values():
            try:
                if adapter.wait_object == io_obj:
                    adapter_readable = True
                    break
            except BaseException:
                # Adapter validation will fail the affected jobs before the
                # next wait; never hide that failure behind refresh bookkeeping.
                continue
        self._io_wait_set.set_interest(
            io_obj,
            io_obj in self.ioReadWaiters or adapter_readable,
            io_obj in self.ioWriteWaiters,
        )

    def _wake_io_tasks(self, timeout_ms: int | None = 0):
        """
        Poll user I/O and adapter completion sources in one kernel wait.

        Adapter worker threads only make their completion socket readable. All
        queue mutation and task resumption still happens on this scheduler
        thread.
        """
        if not self.kernel or not hasattr(self.kernel, "io_wait"):
            return
        if not self.ioReadWaiters and not self.ioWriteWaiters and not self._adapter_jobs:
            return

        self._fail_invalid_io_waiters()
        adapter_sources = self._collect_adapter_sources()
        if not self.ioReadWaiters and not self.ioWriteWaiters and not adapter_sources:
            return

        readables = list(self.ioReadWaiters.keys())
        for wait_object in adapter_sources:
            if wait_object not in self.ioReadWaiters:
                readables.append(wait_object)

        adapter_job_count = len(self._adapter_jobs)
        io_waiter_count = len(self.ioReadWaiters) + len(self.ioWriteWaiters)
        try:
            if self._io_wait_set is not None:
                for wait_object in adapter_sources:
                    self._refresh_io_interest(wait_object)
                readable, writable = self._io_wait_set.wait(timeout_ms)
            else:
                readable, writable = self.kernel.io_wait(
                    readables,
                    list(self.ioWriteWaiters.keys()),
                    timeout_ms,
                )
        except Exception:
            # A completion channel may close after validation but before poll
            # registration. Revalidate once and recover if that race removed a
            # broken source; otherwise preserve the kernel's original failure.
            self._fail_invalid_io_waiters()
            self._collect_adapter_sources()
            if (
                len(self._adapter_jobs) < adapter_job_count
                or len(self.ioReadWaiters) + len(self.ioWriteWaiters) < io_waiter_count
            ):
                return
            raise
        self._resume_ready_io(readable, writable)
        for ready_object in readable:
            adapter = adapter_sources.get(ready_object)
            if adapter is not None:
                self._drain_adapter_completions(adapter)

    def _collect_adapter_sources(self) -> dict[Any, ExecutionAdapterLike]:
        """Return valid completion wait objects for adapters with live jobs."""
        adapters: list[ExecutionAdapterLike] = []
        for adapter, _task in list(self._adapter_jobs.values()):
            if not any(existing is adapter for existing in adapters):
                adapters.append(adapter)

        sources: dict[Any, ExecutionAdapterLike] = {}
        validator = getattr(self.kernel, "validate_io_wait_object", None)
        for adapter in adapters:
            try:
                is_closed = adapter.closed
                if type(is_closed) is not bool:
                    raise AdapterProtocolError(
                        "{} closed state must be boolean".format(
                            self._adapter_name(adapter)
                        )
                    )
            except BaseException as exc:
                self._fail_adapter_jobs(
                    adapter,
                    AdapterProtocolError(
                        "{} closed-state check failed: {}".format(
                            self._adapter_name(adapter),
                            exc,
                        )
                    ),
                )
                continue
            if is_closed:
                self._fail_adapter_jobs(
                    adapter,
                    AdapterClosedError(
                        "{} closed with jobs still pending".format(
                            self._adapter_name(adapter)
                        )
                    ),
                )
                continue
            try:
                wait_object = adapter.wait_object
                hash(wait_object)
            except BaseException as exc:
                self._fail_adapter_jobs(
                    adapter,
                    AdapterProtocolError(
                        "{} completion wait object failed: {}".format(
                            self._adapter_name(adapter),
                            exc,
                        )
                    ),
                )
                continue

            if validator is not None:
                try:
                    is_valid, exc = validator(wait_object)
                except BaseException as exc:
                    self._fail_adapter_jobs(
                        adapter,
                        AdapterUnavailableError(
                            "{} could not validate its completion wait object: {}".format(
                                self._adapter_name(adapter),
                                exc,
                            )
                        ),
                    )
                    continue
                if not is_valid:
                    self._fail_adapter_jobs(
                        adapter,
                        AdapterUnavailableError(
                            "{} completion wait object became invalid: {}".format(
                                self._adapter_name(adapter),
                                exc,
                            )
                        ),
                    )
                    continue
            if wait_object in sources and sources[wait_object] is not adapter:
                self._fail_adapter_jobs(
                    adapter,
                    AdapterProtocolError(
                        "adapter completion wait objects must be unique"
                    ),
                )
                continue
            sources[wait_object] = adapter
        return sources

    def _drain_adapter_completions(self, adapter: ExecutionAdapterLike) -> None:
        """Resume SmallTasks from every completion currently queued."""
        try:
            completions = adapter.drain_completions()
            if completions is None:
                raise AdapterProtocolError(
                    "{} drain_completions() returned None".format(
                        self._adapter_name(adapter)
                    )
                )
            completions = list(completions)
        except BaseException as exc:
            self._fail_adapter_jobs(
                adapter,
                self._safe_adapter_exception(adapter, exc),
            )
            return

        for completion in completions:
            try:
                job_id = completion.job_id
                if type(job_id) is not int or job_id <= 0:
                    raise AdapterProtocolError(
                        "adapter completion job_id must be a positive integer"
                    )
                cancelled = completion.cancelled
                if type(cancelled) is not bool:
                    raise AdapterProtocolError(
                        "adapter completion cancelled state must be boolean"
                    )
                exception = completion.exception
                if exception is not None and not isinstance(
                    exception,
                    BaseException,
                ):
                    raise AdapterProtocolError(
                        "adapter completion exception must derive from BaseException"
                    )
                has_value = completion.has_value
                if type(has_value) is not bool:
                    raise AdapterProtocolError(
                        "adapter completion has_value state must be boolean"
                    )
                value = completion.value if has_value else _MISSING
                outcome_count = int(cancelled) + int(exception is not None) + int(has_value)
                if outcome_count != 1:
                    raise AdapterProtocolError(
                        "adapter completion must contain exactly one outcome"
                    )
            except BaseException as exc:
                self._fail_adapter_jobs(
                    adapter,
                    self._safe_adapter_exception(adapter, exc),
                )
                return

            entry = self._adapter_jobs.get(job_id)
            if entry is None:
                # A cancelled SmallTask may leave a late foreign completion.
                continue
            entry_adapter, task = entry
            if entry_adapter is not adapter:
                self._fail_adapter_jobs(
                    adapter,
                    AdapterProtocolError(
                        "{} completed job {} owned by another adapter".format(
                            self._adapter_name(adapter),
                            job_id,
                        )
                    ),
                )
                return

            self._adapter_jobs.pop(job_id, None)
            if task.done or self.tasks.search(task.getID()) == -1:
                continue

            if cancelled:
                exc = AdapterCancelledError(
                    "{} job {} was cancelled by the foreign runtime".format(
                        self._adapter_name(adapter),
                        job_id,
                    )
                )
                self._record_adapter_resume_origin(task, adapter, job_id)
                self.resume_task(task, exc=exc, front=True)
                continue

            if exception is not None:
                safe_exc = self._safe_adapter_exception(adapter, exception)
                self._record_adapter_resume_origin(task, adapter, job_id)
                self.resume_task(task, exc=safe_exc, front=True)
                continue

            self.resume_task(task, value=value, front=True)

        try:
            self._refresh_io_interest(adapter.wait_object)
        except BaseException:
            # The next source collection turns a broken completion object into
            # a task-level adapter error rather than breaking scheduler cleanup.
            pass

    def _fail_adapter_jobs(
        self,
        adapter: ExecutionAdapterLike,
        exc: BaseException,
    ) -> None:
        """Fail every live SmallTask waiting on a broken adapter source."""
        jobs = [
            (job_id, task)
            for job_id, (job_adapter, task) in list(self._adapter_jobs.items())
            if job_adapter is adapter
        ]
        for job_id, task in jobs:
            self._adapter_jobs.pop(job_id, None)
            try:
                adapter.cancel(job_id)
            except BaseException:
                pass
            if task.done or self.tasks.search(task.getID()) == -1:
                continue
            task_exc = self._clone_adapter_error(exc)
            self._record_adapter_resume_origin(task, adapter, job_id)
            self.resume_task(task, exc=task_exc, front=True)
        try:
            self._refresh_io_interest(adapter.wait_object)
        except BaseException:
            pass

    def _clone_adapter_error(self, exc: BaseException) -> Exception:
        """Create a per-task adapter exception when one source fails broadly."""
        safe_exc = self._safe_adapter_exception(None, exc)
        args = getattr(safe_exc, "args", ())
        try:
            return safe_exc.__class__(*args)
        except Exception:
            return AdapterUnavailableError(str(safe_exc))

    def _fail_invalid_io_waiters(self):
        """
        Resume waiters whose I/O objects are already closed or otherwise invalid.

        Poll/select backends raise immediately when handed a stale descriptor,
        which would otherwise take down the whole runtime before the affected
        task can observe the problem.
        """
        validator = getattr(self.kernel, "validate_io_wait_object", None)
        if validator is None:
            return
        io_objects = list(self.ioReadWaiters.keys())
        for io_obj in self.ioWriteWaiters:
            if io_obj not in self.ioReadWaiters:
                io_objects.append(io_obj)

        for io_obj in io_objects:
            is_valid, exc = validator(io_obj)
            if is_valid:
                continue

            waiters = self.ioReadWaiters.pop(io_obj, [])
            for waiter in self.ioWriteWaiters.pop(io_obj, []):
                if waiter not in waiters:
                    waiters.append(waiter)
            self._refresh_io_interest(io_obj)
            for waiter in waiters:
                if waiter.done or self.tasks.search(waiter.getID()) == -1:
                    continue
                self.resume_task(waiter, exc=self._clone_wait_error(exc), front=True)

    def _clone_wait_error(self, exc):
        """Return a fresh exception instance for resuming a blocked waiter."""
        if isinstance(exc, BaseException):
            args = getattr(exc, "args", ())
            try:
                return exc.__class__(*args)
            except Exception:
                return RuntimeError(str(exc))
        return RuntimeError("I/O wait object is no longer valid.")

    def _resume_ready_io(self, readable, writable):
        """Detach one readiness snapshot before applying registration deltas."""
        batches = []
        changed_objects = []
        for ready_objects, waiters_map in (
            (readable, self.ioReadWaiters),
            (writable, self.ioWriteWaiters),
        ):
            for io_obj in ready_objects:
                waiters = waiters_map.pop(io_obj, [])
                batches.append((io_obj, waiters))
                if io_obj not in changed_objects:
                    changed_objects.append(io_obj)

        # An object ready for both directions should move directly from its
        # combined mask to its final mask instead of modify-then-unregister.
        for io_obj in changed_objects:
            self._refresh_io_interest(io_obj)

        for io_obj, waiters in batches:
            for waiter in waiters:
                if waiter.done or self.tasks.search(waiter.getID()) == -1:
                    continue
                self.resume_task(waiter, value=io_obj, front=True)

    def _clear_wait_registration(self, task):
        """
        Remove a task from any registration-based wait bookkeeping.

        This prevents leaked waiter references when a task is resumed,
        cancelled, or moved from one wait condition to another.
        """
        if task._join_target is not None:
            task._join_target.discard_join_waiter(task)

        if task._join_targets:
            for child in task._join_targets:
                child.discard_join_waiter(task)

        if task._io_wait_obj is not None and task._io_wait_mode is not None:
            io_obj = task._io_wait_obj
            waiters_map = self.ioReadWaiters if task._io_wait_mode == "read" else self.ioWriteWaiters
            waiters = waiters_map.get(io_obj, [])
            while task in waiters:
                waiters.remove(task)
            if not waiters and io_obj in waiters_map:
                del waiters_map[io_obj]
                self._refresh_io_interest(io_obj)

        if task._adapter_job_id is not None:
            job_id = task._adapter_job_id
            entry = self._adapter_jobs.pop(job_id, None)
            adapter = task._adapter
            if entry is not None:
                adapter = entry[0]
            if adapter is not None and entry is not None:
                try:
                    adapter.cancel(job_id)
                except BaseException:
                    pass
                try:
                    self._refresh_io_interest(adapter.wait_object)
                except BaseException:
                    pass

    def _should_dispatch_failure(self, task):
        """Return whether ``task`` should produce a runtime failure event."""
        exc = task.exception
        if exc is None:
            return False
        if isinstance(exc, TaskCancelledError) and not self.errorHandlerIncludeCancelled:
            return False
        return True

    def _snapshot_task_id(self, task):
        """Return a task or PID reference as a PID integer when possible."""
        if task is None or task == -1:
            return None
        if hasattr(task, "getID"):
            return task.getID()
        if isinstance(task, int):
            return task
        return None

    def _format_exception_traceback(self, exc):
        """Return a best-effort formatted traceback string for ``exc``."""
        try:
            import traceback
        except ImportError:
            return None

        try:
            return "".join(
                traceback.format_exception(type(exc), exc, getattr(exc, "__traceback__", None))
            )
        except Exception:
            try:
                return "".join(traceback.format_exception_only(type(exc), exc))
            except Exception:
                return None

    def _build_failure_event(self, task):
        """Snapshot the task failure context before finalization clears wait state."""
        exc = task.exception
        adapter_name = task._adapter_resume_name
        adapter_job_id = task._adapter_resume_job_id
        if adapter_name is None and task._adapter is not None:
            adapter_name = self._adapter_name(task._adapter)
            adapter_job_id = task._adapter_job_id
        return {
            "task_id": task.getID(),
            "task_name": task.name,
            "parent_id": self._snapshot_task_id(task.parent),
            "exception": exc,
            "exception_type": type(exc).__name__ if exc is not None else None,
            "exception_repr": repr(exc),
            "is_cancelled": isinstance(exc, TaskCancelledError),
            "blocked_reason": task._blocked_reason,
            "waiting_signal": task._waiting_signal,
            "io_wait_mode": task._io_wait_mode,
            "join_target_id": self._snapshot_task_id(task._join_target),
            "join_pending_ids": sorted(task._join_pending) if task._join_pending else [],
            "traceback_text": self._format_exception_traceback(exc),
            "adapter_name": adapter_name,
            "adapter_job_id": adapter_job_id,
        }

    def _write_runtime_diagnostic(self, message):
        """Write a best-effort runtime diagnostic without crashing the scheduler."""
        if not message:
            return
        if not message.endswith("\n"):
            message += "\n"
        try:
            if self.kernel and hasattr(self.kernel, "write"):
                self.kernel.write(message)
        except Exception:
            return

    def _dispatch_error_handler(self, event):
        """Invoke the installed runtime error handler without surfacing its failures."""
        if self.errorHandler is None:
            return
        try:
            self.errorHandler(event)
        except Exception as exc:
            diagnostic = self._format_exception_traceback(exc) or repr(exc)
            self._write_runtime_diagnostic(
                "smallOS error handler failed: {}".format(diagnostic.rstrip("\n"))
            )

    def _detach_from_parent(self, task):
        """Remove a finished child PID from its parent's child list."""
        parent = task.parent
        if not parent or parent == -1 or not hasattr(parent, "children"):
            return
        while task.getID() in parent.children:
            parent.children.remove(task.getID())

    def _notify_waiters(self, task):
        """
        Wake every task that was blocked on this task's completion.

        ``join`` waiters receive a single result or exception. ``join_all``
        waiters either fail fast on the first child exception or resume when all
        children have finished.
        """
        waiters = list(task._join_waiters)
        task._join_waiters = []

        for waiter in waiters:
            if waiter.done:
                continue
            if self.tasks.search(waiter.getID()) == -1:
                continue

            if waiter._blocked_reason == "join" and waiter._join_target is task:
                self._resume_from_completed(waiter, task)
                continue

            if waiter._blocked_reason == "join_all" and waiter._join_targets:
                if task.exception is not None:
                    # ``join_all`` behaves like structured concurrency here:
                    # one child failure wakes the parent immediately.
                    self.resume_task(waiter, exc=task.exception, front=True)
                    continue

                waiter._join_pending.discard(task.getID())
                if not waiter._join_pending:
                    results = [child.result for child in waiter._join_targets]
                    self.resume_task(waiter, value=results, front=True)

    def _finalize_task(self, task):
        """Run the full shutdown sequence for a finished or cancelled task."""
        failure_event = None
        if self._should_dispatch_failure(task):
            failure_event = self._build_failure_event(task)
        self._clear_wait_state(task)
        self._notify_waiters(task)
        self._detach_from_parent(task)
        self.tasks.delete(task.getID())
        self._clear_adapter_resume_origin(task)
        if failure_event is not None:
            self._dispatch_error_handler(failure_event)

    def cancel_task(self, task: int | SmallTask, recursive: bool = False) -> int:
        """Cancel a task by object or PID and optionally cancel its descendants."""
        target = self._resolve_task(task)
        if target is None or target == -1:
            return -1

        if recursive:
            for child_id in list(target.children):
                child = self.tasks.search(child_id)
                if child != -1:
                    self.cancel_task(child, recursive=True)

        # Remove any active wait registrations before cancellation resets task
        # bookkeeping fields. This prevents stale I/O waiters from surviving
        # after the task is gone.
        self._clear_wait_registration(target)
        target.cancel()
        self._finalize_task(target)
        return 0

    def __str__(self) -> str:
        """Return a human-readable dump of the currently registered tasks."""
        all_tasks = list(self.tasks.tasks)
        string = "SmallOS\n"
        for count, routine in enumerate(all_tasks):
            string += str(count + 1) + ". " + str(routine) + "\n"
        return string
