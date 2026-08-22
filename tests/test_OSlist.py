import sys
import unittest

sys.path.append("..")

from SmallPackage.OSlist import OSList
from SmallPackage.SmallTask import SmallTask


class TestOSList(unittest.TestCase):
    def test_insert_assigns_incrementing_pids(self):
        tasks = OSList(10)
        inserted = [SmallTask((index % 9) + 1, None, name=str(index)) for index in range(32)]

        for task in inserted:
            tasks.insert(task)

        self.assertEqual(list(range(32)), [task.pid for task in tasks.list()])

    def test_pop_respects_priority_order(self):
        tasks = OSList(10)
        items = [
            SmallTask(5, None, name="slow"),
            SmallTask(1, None, name="fast"),
            SmallTask(3, None, name="medium"),
        ]

        for task in items:
            tasks.insert(task)
            tasks.enqueue(task)

        popped = [tasks.pop(), tasks.pop(), tasks.pop()]
        self.assertEqual(["fast", "medium", "slow"], [task.name for task in popped])

    def test_same_priority_is_fifo_and_front_resume_runs_first(self):
        tasks = OSList(4)
        first = SmallTask(2, None, name="first")
        second = SmallTask(2, None, name="second")
        resumed = SmallTask(2, None, name="resumed")

        for task in (first, second, resumed):
            tasks.insert(task)
        tasks.enqueue(first)
        tasks.enqueue(second)
        tasks.enqueue(resumed, front=True)

        self.assertEqual(
            ["resumed", "first", "second"],
            [tasks.pop().name, tasks.pop().name, tasks.pop().name],
        )

    def test_search_and_delete(self):
        tasks = OSList(10)
        task = SmallTask(2, None, name="worker")
        pid = tasks.insert(task)

        self.assertIs(tasks.search(pid), task)
        self.assertEqual(0, tasks.delete(pid))
        self.assertEqual(-1, tasks.search(pid))

    def test_has_ready_preserves_live_task_and_discards_stale_entries(self):
        tasks = OSList(10)
        stale = SmallTask(1, None, name="stale")
        live = SmallTask(2, None, name="live")
        for task in (stale, live):
            tasks.insert(task)
            tasks.enqueue(task)
        tasks.delete(stale.getID())

        self.assertTrue(tasks.has_ready())
        self.assertFalse(stale._queued)
        self.assertIs(live, tasks.pop())
        self.assertFalse(tasks.has_ready())

    def test_capacity_exhaustion_and_pid_reuse(self):
        tasks = OSList(4, length=2)
        first = SmallTask(1, None, name="first")
        second = SmallTask(1, None, name="second")
        overflow = SmallTask(1, None, name="overflow")

        self.assertEqual(0, tasks.insert(first))
        self.assertEqual(1, tasks.insert(second))
        self.assertEqual(-1, tasks.insert(overflow))

        self.assertEqual(0, tasks.delete(first.getID()))
        replacement = SmallTask(1, None, name="replacement")
        self.assertEqual(0, tasks.insert(replacement))
        self.assertIs(replacement, tasks.search(0))

    def test_invalid_priority_does_not_consume_a_pid(self):
        tasks = OSList(4, length=1)
        invalid = SmallTask(4, None, name="invalid")
        valid = SmallTask(1, None, name="valid")

        self.assertEqual(-1, tasks.insert(invalid))
        self.assertEqual(0, tasks.insert(valid))

    def test_delete_removes_queued_task_before_pid_reuse(self):
        tasks = OSList(4, length=1)
        stale = SmallTask(1, None, name="stale")
        tasks.insert(stale)
        tasks.enqueue(stale)

        self.assertEqual(0, tasks.delete(stale.getID()))
        self.assertFalse(stale._queued)

        replacement = SmallTask(1, None, name="replacement")
        tasks.insert(replacement)
        tasks.enqueue(replacement)

        self.assertIs(replacement, tasks.pop())
        self.assertIsNone(tasks.pop())

    def test_sleep_heap_rejects_stale_task_after_pid_reuse(self):
        tasks = OSList(4, length=1)
        stale = SmallTask(1, None, name="stale")
        tasks.insert(stale)
        stale.block("sleep")
        tasks.add_sleeping(stale, 10)
        tasks.delete(stale.getID())

        replacement = SmallTask(1, None, name="replacement")
        tasks.insert(replacement)

        self.assertEqual([], tasks.wake_sleeping(10))
        self.assertIsNone(tasks.next_wake_time())

    def test_watcher_accounting_tracks_insert_and_delete(self):
        tasks = OSList(4)
        watcher = SmallTask(1, None, name="watcher", isWatcher=True)
        worker = SmallTask(1, None, name="worker")

        tasks.insert(watcher)
        self.assertTrue(tasks.isOnlyWatchers())
        tasks.insert(worker)
        self.assertFalse(tasks.isOnlyWatchers())
        tasks.delete(worker.getID())
        self.assertTrue(tasks.isOnlyWatchers())
        tasks.delete(watcher.getID())
        self.assertEqual(0, tasks.numWatchers)

    def test_list_remains_sorted_by_pid_after_reuse(self):
        tasks = OSList(4, length=3)
        first = SmallTask(1, None, name="first")
        middle = SmallTask(1, None, name="middle")
        last = SmallTask(1, None, name="last")
        for task in (first, middle, last):
            tasks.insert(task)

        tasks.delete(middle.getID())
        replacement = SmallTask(1, None, name="replacement")
        tasks.insert(replacement)

        self.assertEqual([0, 1, 2], [task.getID() for task in tasks.list()])
        self.assertEqual(["first", "replacement", "last"], [task.name for task in tasks.list()])


if __name__ == "__main__":
    unittest.main()
