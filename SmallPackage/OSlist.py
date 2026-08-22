"""
Task registry and scheduling queues for smallOS.

The runtime needs two different access patterns:
- look up a task quickly by PID
- choose the next runnable task by priority

This module keeps those responsibilities together so the scheduler can stay
small and focused. PID lookup uses a dictionary, ready tasks live in one FIFO
queue per priority, and sleeping tasks live in a wake-time heap.
"""

from __future__ import annotations

from collections import deque
import heapq

try:
    from typing import TYPE_CHECKING
except ImportError:  # pragma: no cover
    TYPE_CHECKING = False

if TYPE_CHECKING:
    from typing import Literal

    from .SmallTask import SmallTask


class OSList:
    """
    Combined PID registry and queue manager for the cooperative scheduler.
    """

    def __init__(self, priors: int = 5, length: int = 2**12) -> None:
        """Create the PID registry plus ready/sleep queue structures."""
        self.num_priorities = priors
        self.maxPID = length
        self._next_pid = 0
        self._tasks_by_pid: dict[int, SmallTask] = {}
        # MicroPython requires both an iterable and maxlen. The total task
        # capacity is also a safe bound for each queue because a task can be
        # present in at most one ready queue once.
        self.ready: list[deque[SmallTask]] = [deque((), length) for _ in range(priors)]
        self.sleeping: list[tuple[int, int, SmallTask]] = []
        self._sleep_seq = 0
        self.numWatchers = 0

    def resetCatSel(self) -> None:
        """Compatibility no-op kept for older callers."""
        return

    def _new_pid(self) -> int:
        """Return the next free PID from the bounded PID namespace."""
        if len(self._tasks_by_pid) >= self.maxPID:
            return -1

        pid = self._next_pid
        while pid in self._tasks_by_pid:
            pid = (pid + 1) % self.maxPID
        self._next_pid = (pid + 1) % self.maxPID
        return pid

    def _is_registered(self, task: SmallTask) -> bool:
        """Check task identity as well as PID to reject stale reused-PID entries."""
        return self._tasks_by_pid.get(task.getID()) is task

    def _remove_ready_entry(self, task: SmallTask) -> None:
        """Eagerly remove a deleted task so bounded queues cannot retain garbage."""
        if not task._queued:
            return

        priority = task.priority
        queue = self.ready[priority]
        retained: deque[SmallTask] = deque((), self.maxPID)
        while queue:
            queued = queue.popleft()
            if queued is not task:
                retained.append(queued)
        self.ready[priority] = retained
        task._queued = False

    def insert(self, task: SmallTask) -> int:
        """Assign a PID and register a task in the PID mapping."""
        priority = task.priority
        if not 0 < priority < self.num_priorities:
            return -1

        pid = self._new_pid()
        if pid == -1:
            return -1

        task.setID(pid)
        if task.isWatcher:
            self.numWatchers += 1

        self._tasks_by_pid[pid] = task
        return pid

    def search(self, pid: int) -> SmallTask | Literal[-1]:
        """Look up a task by PID."""
        return self._tasks_by_pid.get(pid, -1)

    def delete(self, pid: int) -> int:
        """Remove a task from PID storage and watcher accounting."""
        task = self._tasks_by_pid.get(pid)
        if task is None:
            return -1

        self._remove_ready_entry(task)
        if task.isWatcher:
            self.numWatchers -= 1
        del self._tasks_by_pid[pid]
        return 0

    def enqueue(self, task: SmallTask, front: bool = False) -> int:
        """
        Put a runnable task on its per-priority ready queue.

        ``front=True`` is used when a task should resume before other tasks of
        the same priority, such as when a join or signal completes.
        """
        if task == -1 or task is None or task.done:
            return -1
        if not self._is_registered(task):
            return -1
        if task._queued:
            return 0

        queue = self.ready[task.priority]
        if front:
            queue.appendleft(task)
        else:
            queue.append(task)
        task._queued = True
        return 0

    def pop(self) -> SmallTask | None:
        """
        Return the next runnable task.

        Lower numeric priority values run first. Within the same priority,
        arrival order is preserved by the deque.
        """
        for priority in range(1, self.num_priorities):
            queue = self.ready[priority]
            while queue:
                task = queue.popleft()
                task._queued = False
                if not self._is_registered(task):
                    continue
                if not task.getExeStatus():
                    continue
                return task
        return None

    def has_ready(self) -> bool:
        """Return whether a valid runnable task is queued without removing it."""
        for priority in range(1, self.num_priorities):
            queue = self.ready[priority]
            while queue:
                task = queue[0]
                if self._is_registered(task) and task.getExeStatus():
                    return True
                queue.popleft()
                task._queued = False
        return False

    def add_sleeping(self, task: SmallTask, wake_time: int) -> None:
        """Push a sleeping task onto the wake-time heap."""
        self._sleep_seq += 1
        heapq.heappush(self.sleeping, (wake_time, self._sleep_seq, task))

    def wake_sleeping(self, now: int) -> list[SmallTask]:
        """
        Return every task whose scheduled wake time has arrived.

        Stale heap entries are ignored so cancelled or already-resumed tasks do
        not need to be eagerly removed from the heap.
        """
        ready = []
        while self.sleeping and self.sleeping[0][0] <= now:
            _, _, task = heapq.heappop(self.sleeping)
            if not self._is_registered(task):
                continue
            if task.done or task._blocked_reason != "sleep":
                continue
            ready.append(task)
        return ready

    def next_wake_time(self) -> int | None:
        """Peek at the next valid wake time, discarding stale heap entries."""
        while self.sleeping:
            wake_time, _, task = self.sleeping[0]
            if not self._is_registered(task) or task.done or task._blocked_reason != "sleep":
                heapq.heappop(self.sleeping)
                continue
            return wake_time
        return None

    def list(self) -> list[SmallTask]:
        """Return a snapshot list of currently registered tasks."""
        return [self._tasks_by_pid[pid] for pid in sorted(self._tasks_by_pid)]

    def isOnlyWatchers(self) -> bool:
        """Report whether every remaining task is marked as a watcher."""
        return len(self._tasks_by_pid) == self.numWatchers

    def __len__(self) -> int:
        """Return the number of registered tasks."""
        return len(self._tasks_by_pid)

    def __str__(self) -> str:
        """Return a newline-separated dump of all known tasks."""
        return "\n".join(str(task) for task in self.list())
