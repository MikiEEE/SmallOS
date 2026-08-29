# Error Handling and Scheduler Wakeups

[Previous: API reference](api-reference.md) · [Guide home](README.md) ·
[Next: Kernels and MicroPython](kernels-and-micropython.md)

## Observe task failures

Install a runtime-level synchronous error observer with
`setErrorHandler(handler, include_cancelled=False)`:

```python
from SmallPackage import SmallOS, Unix


def log_runtime_error(event):
    print(
        "[smallOS] task failure in {} (PID {}): {}".format(
            event["task_name"] or "unnamed task",
            event["task_id"],
            event["exception_repr"],
        )
    )
    if event["traceback_text"]:
        print(event["traceback_text"], end="")


runtime = SmallOS().setKernel(Unix())
runtime.setErrorHandler(log_runtime_error)
```

The observer runs after the failed task is finalized. Events include task,
parent, exception, cancellation, blocked/waiting, join, adapter, and traceback
details. The currently exposed keys are:

- `task_id`, `task_name`, and `parent_id`
- `exception`, `exception_type`, and `exception_repr`
- `is_cancelled` and `traceback_text`
- `blocked_reason`, `waiting_signal`, and `io_wait_mode`
- `join_target_id` and `join_pending_ids`
- `adapter_name` and `adapter_job_id`

Cancellation events are excluded by default. Pass `include_cancelled=True` to
observe `TaskCancelledError` as well.

## Invalid I/O objects

A closed or invalid file descriptor passed to `wait_readable(...)` or
`wait_writable(...)` fails the waiting task instead of crashing the scheduler
through the platform poll/select layer. The runtime finalizes that task and
delivers its exception—commonly `ValueError`—to the error observer.

## Wake a blocked scheduler from another thread

Some kernels expose an opaque wakeup channel for external threads that need to
request scheduler-owned work, such as server shutdown:

```python
kernel = Unix()
if not kernel.supports_wakeup_channel():
    raise RuntimeError("cross-thread scheduler wakeup is unavailable")

wakeup = kernel.create_wakeup_channel()


async def watch_shutdown(task):
    await task.wait_readable(wakeup.wait_object)
    wakeup.drain()
    # Apply the application-owned request on the scheduler thread.
```

Call `wakeup.notify()` from the external thread. Notifications are nonblocking
and coalesce until the scheduler calls `drain()`. Call `close()` only after the
scheduler wait is detached; repeated close, notify, and drain calls are safe
during teardown.

`Unix` supports this contract when `socketpair()` is available. Generic
`MicroPythonKernel` deliberately reports it unsupported because a polling
backend alone does not establish safe cross-thread behavior on a constrained
port. Scheduler-native shutdown does not need a cross-thread wakeup channel.
