import asyncio
import sqlite3
import subprocess
import sys
import threading
import unittest

sys.path.append("..")

from SmallPackage.Kernel import Kernel, Unix
from SmallPackage.SmallErrors import TaskCancelledError
from SmallPackage.SmallOS import SmallOS
from SmallPackage.SmallTask import SmallTask
from SmallPackage.adapters import (
    AdapterCancelledError,
    AdapterCapacityError,
    AdapterCompletion,
    AdapterProtocolError,
    AdapterUnavailableError,
    ExecutionAdapter,
)
from SmallPackage.adapters._completion import CompletionChannel
from SmallPackage.adapters.asyncio_loop import AsyncioAdapter
from SmallPackage.adapters.threads import ThreadAdapter


class AdapterTestKernel(Kernel):
    """Deterministic readiness kernel for the scheduler contract tests."""

    def __init__(self):
        super().__init__()
        self.now = 0
        self.readable = set()

    def ticks_ms(self):
        return self.now

    def sleep_ms(self, delay_ms):
        self.now += max(0, int(delay_ms))

    def io_wait(self, readables, writables, timeout_ms=None):
        if timeout_ms is not None:
            self.now += max(0, int(timeout_ms))
        ready = [obj for obj in readables if obj in self.readable]
        for obj in ready:
            self.readable.discard(obj)
        return ready, []

    def supports_external_wait_objects(self):
        return True

    def mark_readable(self, obj):
        self.readable.add(obj)


class NoExternalWaitKernel(AdapterTestKernel):
    def supports_external_wait_objects(self):
        return False


class ImmediateAdapter(ExecutionAdapter):
    """No-thread adapter used to test only the scheduler integration."""

    def __init__(self):
        super().__init__("manual")
        self._wait_object = object()
        self._completions = []
        self._pending = set()
        self._closed = False

    @property
    def wait_object(self):
        return self._wait_object

    @property
    def pending_count(self):
        return len(self._pending)

    @property
    def closed(self):
        return self._closed

    def submit(self, job_id, callable_obj, args, kwargs):
        self._pending.add(job_id)
        try:
            value = callable_obj(*args, **kwargs)
        except BaseException as exc:
            completion = AdapterCompletion.failed(job_id, exc)
        else:
            completion = AdapterCompletion.result(job_id, value)
        self._completions.append(completion)
        self._bound_runtime.kernel.mark_readable(self.wait_object)

    def cancel(self, job_id):
        was_pending = job_id in self._pending
        self._pending.discard(job_id)
        return was_pending

    def drain_completions(self):
        completions = list(self._completions)
        self._completions = []
        for completion in completions:
            self._pending.discard(completion.job_id)
        return completions

    def shutdown(self, wait=True, cancel_pending=False):
        self._closed = True


class StructuralCompletion:
    """Completion-shaped object used to exercise runtime validation."""

    def __init__(
        self,
        *,
        job_id,
        value=None,
        exception=None,
        cancelled=False,
        has_value=True,
    ):
        self.job_id = job_id
        self.value = value
        self.exception = exception
        self.cancelled = cancelled
        self.has_value = has_value


class ScriptedCompletionAdapter(ImmediateAdapter):
    """Manual adapter that returns a caller-selected structural completion."""

    def __init__(self, completion_factory):
        super().__init__()
        self._completion_factory = completion_factory

    def submit(self, job_id, callable_obj, args, kwargs):
        self._pending.add(job_id)
        self._completions.append(self._completion_factory(job_id))
        self._bound_runtime.kernel.mark_readable(self.wait_object)


class TestAdapterSchedulerContract(unittest.TestCase):
    def run_task(self, adapter, routine, events=None):
        kernel = AdapterTestKernel()
        runtime = SmallOS().setKernel(kernel)
        task = SmallTask(2, routine, name="adapter-test")
        runtime.fork(task)
        if events is not None:
            runtime.setErrorHandler(events.append)
        runtime.start()
        return task, runtime

    def test_manual_adapter_returns_result_and_keeps_runtime_alive(self):
        adapter = ImmediateAdapter()

        async def routine(task):
            return await adapter.call(lambda left, right: left + right, 20, 22)

        task, runtime = self.run_task(adapter, routine)

        self.assertEqual(42, task.result)
        self.assertEqual({}, runtime._adapter_jobs)
        self.assertIsNone(task._adapter)
        self.assertIsNone(task._adapter_job_id)

    def test_manual_adapter_preserves_library_exception_type(self):
        adapter = ImmediateAdapter()

        class UserLibraryError(Exception):
            pass

        def fail():
            raise UserLibraryError("library failed")

        async def routine(task):
            try:
                await adapter.call(fail)
            except UserLibraryError as exc:
                return str(exc)
            return "missed"

        task, _runtime = self.run_task(adapter, routine)
        self.assertEqual("library failed", task.result)

    def test_uncaught_adapter_failure_includes_resume_origin(self):
        adapter = ImmediateAdapter()
        events = []

        def fail():
            raise ValueError("foreign failure")

        async def routine(task):
            await adapter.call(fail)

        task, _runtime = self.run_task(adapter, routine, events=events)

        self.assertIsInstance(task.exception, ValueError)
        self.assertEqual(1, len(events))
        self.assertEqual("manual", events[0]["adapter_name"])
        self.assertIsInstance(events[0]["adapter_job_id"], int)

    def test_foreign_base_exception_is_normalized(self):
        adapter = ImmediateAdapter()

        def stop():
            raise SystemExit("do not stop SmallOS")

        async def routine(task):
            try:
                await adapter.call(stop)
            except Exception as exc:
                return type(exc).__name__
            return "missed"

        task, _runtime = self.run_task(adapter, routine)
        self.assertEqual("AdapterExecutionError", task.result)

    def test_adapter_requires_kernel_external_wait_capability(self):
        adapter = ImmediateAdapter()
        runtime = SmallOS().setKernel(NoExternalWaitKernel())

        async def routine(task):
            try:
                await adapter.call(lambda: 42)
            except AdapterUnavailableError:
                return "unsupported"
            return "missed"

        target = SmallTask(2, routine, name="unsupported-kernel")
        runtime.fork(target)
        runtime.start()

        self.assertEqual("unsupported", target.result)
        self.assertEqual(0, adapter.pending_count)

    def test_adapter_cannot_be_shared_by_live_runtimes(self):
        adapter = ImmediateAdapter()

        async def first(task):
            return await adapter.call(lambda: "first")

        first_task, _runtime = self.run_task(adapter, first)
        self.assertEqual("first", first_task.result)

        async def second(task):
            try:
                await adapter.call(lambda: "second")
            except AdapterUnavailableError:
                return "bound"
            return "missed"

        second_task, _runtime = self.run_task(adapter, second)
        self.assertEqual("bound", second_task.result)

    def test_core_import_does_not_load_desktop_adapter_backends(self):
        code = (
            "import sys; import SmallPackage; "
            "assert 'SmallPackage.adapters.threads' not in sys.modules; "
            "assert 'SmallPackage.adapters.asyncio_loop' not in sys.modules; "
            "assert 'SmallPackage.adapters._completion' not in sys.modules"
        )
        completed = subprocess.run(
            [sys.executable, "-c", code],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(0, completed.returncode, completed.stderr)

    def test_completion_channel_closes_when_notification_fails(self):
        channel = CompletionChannel()
        channel._writer.close()

        posted = channel.post(AdapterCompletion.result(1, 42))

        self.assertFalse(posted)
        self.assertTrue(channel.closed)
        self.assertEqual(-1, channel.wait_object.fileno())

    def test_adapter_completion_enforces_runtime_invariants(self):
        with self.assertRaises(TypeError):
            AdapterCompletion.result(True, 42)
        with self.assertRaises(ValueError):
            AdapterCompletion.result(0, 42)
        with self.assertRaises(TypeError):
            AdapterCompletion(1, exception="not an exception")
        with self.assertRaises(TypeError):
            AdapterCompletion(1, cancelled=1)

    def test_structural_completion_fields_are_not_truthiness_coerced(self):
        invalid_completions = {
            "boolean job ID": lambda _job_id: StructuralCompletion(
                job_id=True,
                value=42,
            ),
            "non-boolean cancellation": lambda job_id: StructuralCompletion(
                job_id=job_id,
                cancelled="yes",
                has_value=False,
            ),
            "non-boolean value state": lambda job_id: StructuralCompletion(
                job_id=job_id,
                value=42,
                has_value=1,
            ),
            "non-exception failure": lambda job_id: StructuralCompletion(
                job_id=job_id,
                exception="failed",
                has_value=False,
            ),
        }

        for label, completion_factory in invalid_completions.items():
            with self.subTest(label=label):
                adapter = ScriptedCompletionAdapter(completion_factory)

                async def routine(task):
                    try:
                        await adapter.call(lambda: 42)
                    except AdapterProtocolError:
                        return "protocol"
                    return "accepted"

                task, _runtime = self.run_task(adapter, routine)
                self.assertEqual("protocol", task.result)

    def test_structural_adapter_closed_state_must_be_boolean(self):
        class InvalidClosedStateAdapter(ImmediateAdapter):
            @property
            def closed(self):
                return 0

        adapter = InvalidClosedStateAdapter()

        async def routine(task):
            try:
                await adapter.call(lambda: 42)
            except AdapterProtocolError:
                return "protocol"
            return "accepted"

        task, _runtime = self.run_task(adapter, routine)
        self.assertEqual("protocol", task.result)


class TestThreadAdapter(unittest.TestCase):
    def build_runtime(self, *tasks):
        runtime = SmallOS().setKernel(Unix())
        runtime.fork(list(tasks))
        runtime.start()
        return runtime

    def test_thread_adapter_rejects_boolean_capacity_values(self):
        with self.assertRaises(ValueError):
            ThreadAdapter(max_workers=True)
        with self.assertRaises(ValueError):
            ThreadAdapter(max_pending=True)

    def test_thread_adapter_returns_result_and_propagates_exception(self):
        class UserLibraryError(Exception):
            pass

        def fail():
            raise UserLibraryError("thread failure")

        with ThreadAdapter(max_workers=2, max_pending=4) as adapter:
            async def routine(task):
                value = await adapter.call(lambda: 21 * 2)
                try:
                    await adapter.call(fail)
                except UserLibraryError as exc:
                    return value, str(exc)
                return None

            target = SmallTask(2, routine, name="thread-result")
            self.build_runtime(target)

        self.assertEqual((42, "thread failure"), target.result)
        self.assertEqual(0, adapter.pending_count)
        self.assertEqual(-1, adapter.wait_object.fileno())

    def test_thread_adapter_rejects_awaitable_results(self):
        async def async_result():
            return 42

        with ThreadAdapter(max_workers=1, max_pending=2) as adapter:
            async def routine(task):
                try:
                    await adapter.call(async_result)
                except AdapterProtocolError as exc:
                    return "AsyncioAdapter" in str(exc)
                return False

            target = SmallTask(2, routine, name="thread-awaitable")
            self.build_runtime(target)

        self.assertTrue(target.result)

    def test_blocking_thread_does_not_block_other_smallos_tasks(self):
        release = threading.Event()
        events = []

        def blocked_call():
            if not release.wait(2):
                raise TimeoutError("test release was not set")
            return "released"

        with ThreadAdapter(max_workers=1, max_pending=2) as adapter:
            async def waiting(task):
                events.append("waiting-start")
                result = await adapter.call(blocked_call)
                events.append("waiting-end")
                return result

            async def peer(task):
                events.append("peer-ran")
                release.set()
                return "peer"

            waiting_task = SmallTask(1, waiting, name="waiting")
            peer_task = SmallTask(2, peer, name="peer")
            self.build_runtime(waiting_task, peer_task)

        self.assertEqual("released", waiting_task.result)
        self.assertEqual("peer", peer_task.result)
        self.assertEqual(["waiting-start", "peer-ran", "waiting-end"], events)

    def test_thread_adapter_capacity_rejection_is_catchable(self):
        release = threading.Event()

        def blocked_call():
            if not release.wait(2):
                raise TimeoutError("test release was not set")
            return "first"

        with ThreadAdapter(max_workers=1, max_pending=1) as adapter:
            async def first(task):
                return await adapter.call(blocked_call)

            async def second(task):
                try:
                    await adapter.call(lambda: "second")
                except AdapterCapacityError:
                    release.set()
                    return "capacity"
                return "missed"

            first_task = SmallTask(1, first, name="first")
            second_task = SmallTask(2, second, name="second")
            self.build_runtime(first_task, second_task)

        self.assertEqual("first", first_task.result)
        self.assertEqual("capacity", second_task.result)

    def test_one_worker_preserves_thread_affinity_across_calls(self):
        thread_ids = []

        def record_thread():
            thread_id = threading.get_ident()
            thread_ids.append(thread_id)
            return thread_id

        with ThreadAdapter(max_workers=1, max_pending=4) as adapter:
            async def routine(task):
                first = await adapter.call(record_thread)
                second = await adapter.call(record_thread)
                return first, second

            target = SmallTask(2, routine, name="affinity")
            self.build_runtime(target)

        self.assertEqual(2, len(thread_ids))
        self.assertEqual(thread_ids[0], thread_ids[1])
        self.assertEqual(tuple(thread_ids), target.result)

    def test_user_owned_sqlite_connection_can_stay_on_one_worker(self):
        state = {}

        def open_database():
            connection = sqlite3.connect(":memory:")
            connection.execute("CREATE TABLE records (value INTEGER)")
            connection.execute("INSERT INTO records VALUES (42)")
            state["connection"] = connection

        def read_database():
            return state["connection"].execute(
                "SELECT value FROM records"
            ).fetchone()[0]

        def close_database():
            state.pop("connection").close()

        with ThreadAdapter(max_workers=1, max_pending=4) as adapter:
            async def routine(task):
                await adapter.call(open_database)
                try:
                    return await adapter.call(read_database)
                finally:
                    await adapter.call(close_database)

            target = SmallTask(2, routine, name="sqlite-user-resource")
            self.build_runtime(target)

        self.assertEqual(42, target.result)
        self.assertEqual({}, state)

    def test_cancelling_thread_waiter_discards_late_completion(self):
        started = threading.Event()
        release = threading.Event()

        def blocked_call():
            started.set()
            release.wait(2)
            return "late"

        with ThreadAdapter(max_workers=1, max_pending=2) as adapter:
            async def waiting(task):
                return await adapter.call(blocked_call)

            async def killer(task, target):
                while not started.is_set():
                    await task.yield_now()
                target.kill()
                release.set()
                return "killed"

            waiting_task = SmallTask(1, waiting, name="waiting")
            killer_task = SmallTask(2, killer, name="killer", args=(waiting_task,))
            self.build_runtime(waiting_task, killer_task)

        self.assertIsInstance(waiting_task.exception, TaskCancelledError)
        self.assertEqual("killed", killer_task.result)
        self.assertEqual(0, adapter.pending_count)

    def test_thread_shutdown_can_escalate_from_nonblocking_to_waiting(self):
        started = threading.Event()
        release = threading.Event()

        def blocked_call():
            started.set()
            release.wait(2)

        adapter = ThreadAdapter(max_workers=1, max_pending=1)
        adapter.submit(1, blocked_call, (), {})
        self.assertTrue(started.wait(1))
        adapter.shutdown(wait=False)
        release.set()

        adapter.shutdown(wait=True)

        self.assertEqual(0, adapter.pending_count)
        self.assertEqual(-1, adapter.wait_object.fileno())


class TestAsyncioAdapter(unittest.TestCase):
    def build_runtime(self, *tasks):
        runtime = SmallOS().setKernel(Unix())
        runtime.fork(list(tasks))
        runtime.start()
        return runtime

    def test_asyncio_adapter_rejects_boolean_limits(self):
        with self.assertRaises(ValueError):
            AsyncioAdapter(max_pending=True)
        with self.assertRaises(ValueError):
            AsyncioAdapter(startup_timeout=True)

    def test_asyncio_adapter_reuses_persistent_loop_thread(self):
        async def identify():
            await asyncio.sleep(0)
            return id(asyncio.get_running_loop()), threading.get_ident()

        scheduler_thread = threading.get_ident()
        with AsyncioAdapter(max_pending=4) as adapter:
            async def routine(task):
                first = await adapter.call(identify)
                second = await adapter.call(identify)
                return first, second

            target = SmallTask(2, routine, name="asyncio-identity")
            self.build_runtime(target)

        first, second = target.result
        self.assertEqual(first, second)
        self.assertNotEqual(scheduler_thread, first[1])
        self.assertIsNone(adapter.shutdown_error)
        self.assertEqual(-1, adapter.wait_object.fileno())

    def test_unexpected_loop_stop_is_observable(self):
        adapter = AsyncioAdapter(max_pending=1)

        async def stop_loop():
            asyncio.get_running_loop().stop()
            return "stopped"

        adapter.submit(1, stop_loop, (), {})
        adapter._thread.join(1)

        self.assertFalse(adapter._thread.is_alive())
        self.assertIsInstance(adapter.shutdown_error, AdapterUnavailableError)
        self.assertTrue(adapter.closed)
        adapter.shutdown()

    def test_asyncio_resources_can_be_reused_on_the_adapter_loop(self):
        state = {}

        async def create_resource():
            loop = asyncio.get_running_loop()
            state["future"] = loop.create_future()
            return id(loop)

        async def use_resource():
            loop = asyncio.get_running_loop()
            future = state.pop("future")
            future.set_result(42)
            return id(loop), await future

        with AsyncioAdapter(max_pending=4) as adapter:
            async def routine(task):
                created_loop = await adapter.call(create_resource)
                used_loop, value = await adapter.call(use_resource)
                return created_loop, used_loop, value

            target = SmallTask(2, routine, name="asyncio-resource")
            self.build_runtime(target)

        created_loop, used_loop, value = target.result
        self.assertEqual(created_loop, used_loop)
        self.assertEqual(42, value)
        self.assertEqual({}, state)

    def test_asyncio_library_wait_does_not_block_smallos(self):
        release = threading.Event()
        events = []

        async def blocked_call():
            while not release.is_set():
                await asyncio.sleep(0)
            return "released"

        with AsyncioAdapter(max_pending=4) as adapter:
            async def waiting(task):
                events.append("waiting-start")
                value = await adapter.call(blocked_call)
                events.append("waiting-end")
                return value

            async def peer(task):
                events.append("peer-ran")
                release.set()
                return "peer"

            waiting_task = SmallTask(1, waiting, name="waiting")
            peer_task = SmallTask(2, peer, name="peer")
            self.build_runtime(waiting_task, peer_task)

        self.assertEqual("released", waiting_task.result)
        self.assertEqual("peer", peer_task.result)
        self.assertEqual(["waiting-start", "peer-ran", "waiting-end"], events)

    def test_asyncio_exception_protocol_and_cancellation_are_catchable(self):
        class UserAsyncError(Exception):
            pass

        async def fail():
            raise UserAsyncError("async failure")

        async def cancel_self():
            raise asyncio.CancelledError()

        with AsyncioAdapter(max_pending=4) as adapter:
            async def routine(task):
                outcomes = []
                try:
                    await adapter.call(fail)
                except UserAsyncError as exc:
                    outcomes.append(str(exc))
                try:
                    await adapter.call(lambda: 42)
                except AdapterProtocolError:
                    outcomes.append("protocol")
                try:
                    await adapter.call(cancel_self)
                except AdapterCancelledError:
                    outcomes.append("cancelled")
                return outcomes

            target = SmallTask(2, routine, name="async-errors")
            self.build_runtime(target)

        self.assertEqual(["async failure", "protocol", "cancelled"], target.result)

    def test_asyncio_adapter_rejects_future_from_another_loop(self):
        other_loop = asyncio.new_event_loop()
        foreign_future = other_loop.create_future()
        try:
            with AsyncioAdapter(max_pending=2) as adapter:
                async def routine(task):
                    try:
                        await adapter.call(lambda: foreign_future)
                    except AdapterProtocolError as exc:
                        return "another event loop" in str(exc)
                    return False

                target = SmallTask(2, routine, name="foreign-future")
                self.build_runtime(target)
        finally:
            foreign_future.cancel()
            other_loop.close()

        self.assertTrue(target.result)

    def test_asyncio_capacity_rejection_is_catchable(self):
        release = threading.Event()

        async def blocked_call():
            while not release.is_set():
                await asyncio.sleep(0)
            return "first"

        with AsyncioAdapter(max_pending=1) as adapter:
            async def first(task):
                return await adapter.call(blocked_call)

            async def second(task):
                try:
                    await adapter.call(asyncio.sleep, 0)
                except AdapterCapacityError:
                    release.set()
                    return "capacity"
                return "missed"

            first_task = SmallTask(1, first, name="first")
            second_task = SmallTask(2, second, name="second")
            self.build_runtime(first_task, second_task)

        self.assertEqual("first", first_task.result)
        self.assertEqual("capacity", second_task.result)

    def test_cancelling_smallos_task_cancels_asyncio_task(self):
        started = threading.Event()
        cleaned_up = threading.Event()

        async def blocked_call():
            started.set()
            try:
                await asyncio.sleep(10)
            finally:
                cleaned_up.set()

        with AsyncioAdapter(max_pending=2) as adapter:
            async def waiting(task):
                return await adapter.call(blocked_call)

            async def killer(task, target):
                while not started.is_set():
                    await task.yield_now()
                target.kill()
                return "killed"

            waiting_task = SmallTask(1, waiting, name="waiting")
            killer_task = SmallTask(2, killer, name="killer", args=(waiting_task,))
            self.build_runtime(waiting_task, killer_task)

        self.assertIsInstance(waiting_task.exception, TaskCancelledError)
        self.assertEqual("killed", killer_task.result)
        self.assertTrue(cleaned_up.is_set())
        self.assertFalse(adapter._thread.is_alive())


if __name__ == "__main__":
    unittest.main()
