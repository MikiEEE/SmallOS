# Task Lifecycle and Coordination

[Previous: Runtime concepts](runtime-concepts.md) · [Guide home](README.md) ·
[Next: Configuration](configuration.md)

## Create and register tasks

A task routine normally accepts its attached `SmallTask` as its first argument:

```python
from SmallPackage import SmallOS, SmallTask, Unix


async def sensor(task, channel, interval):
    while True:
        reading = read_sensor(channel)
        task.OS.print("channel {}: {}\n".format(channel, reading))
        await task.sleep(interval)


runtime = SmallOS().setKernel(Unix())
sensor_task = SmallTask(
    2,
    sensor,
    name="sensor",
    args=(3, 0.25),
)
pid = runtime.fork(sensor_task)
runtime.start()
```

`runtime.fork(task)` returns one PID. Passing a list returns the PIDs in input
order. Registration assigns the PID, attaches the runtime, and queues a ready
task; it does not execute the routine immediately.

Useful constructor options include:

- `name`: diagnostic name shown by the shell and failure observer
- `args`: tuple/list for positional arguments, dictionary for keyword arguments,
  or one value passed as the second routine argument
- `isReady`: whether the task enters the ready queue immediately
- `isWatcher`: whether the task represents background/watch-only work

Priorities run from `1` through `priority_levels - 1`. Lower numbers run first.

## Spawn child tasks

Inside a running task, use `spawn()` to create a parent/child relationship:

```python
async def child(task, value):
    await task.sleep(0.05)
    return value * 2


async def parent(task):
    work = task.spawn(child, priority=2, name="child", args=(21,))
    answer = await task.join(work)
    return answer
```

`spawn()` returns the child task object. If `priority` is omitted, the child
inherits the parent's priority. The older `task.fork(SmallTask(...))` wrapper
returns a PID and remains available for compatibility, but new task code should
prefer `spawn()`.

## Join results and failures

`await task.join(child)` returns the child's result. If the child fails or is
cancelled, its exception is raised into the waiting parent.

`await task.join_all(children)` returns results in the caller-supplied order,
not completion order:

```python
async def parent(task):
    first = task.spawn(child, priority=4, args=(10,))
    second = task.spawn(child, priority=2, args=(20,))
    results = await task.join_all([first, second])
    return results  # [20, 40]
```

Duplicate targets are joined once. An unknown PID is invalid. If any joined
child fails, the first observed child exception wakes the parent immediately;
other children are not automatically cancelled.

A retained task object exposes terminal `done`, `result`, and `exception`
properties even after the runtime removes it from the live PID registry.

## Signals

Signals are application-defined integer slots from `0` through `31`. Use named
constants in application code:

```python
REFRESH_SIGNAL = 3


async def receiver(task):
    signal_number = await task.wait_signal(REFRESH_SIGNAL)
    return signal_number


async def sender(task, target):
    status = task.sendSignal(target.getID(), REFRESH_SIGNAL)
    if status != 0:
        raise RuntimeError("target task is unavailable")
```

A signal delivered before `wait_signal()` is latched, so the later wait can
consume it immediately. `sendSignal()` returns `0` on success and `-1` for an
invalid signal, missing runtime, or unknown PID. `getSignals()` reports latched
signals and `checkSignal(sig)` consumes one without awaiting it.

## Cooperative waiting

The scheduler understands only smallOS-owned awaitables:

- `await task.sleep(seconds)` resumes after a monotonic deadline
- `await task.yield_now()` voluntarily returns to the ready queue
- `await task.wait_signal(signal)` waits for an integer signal slot
- `await task.wait_readable(obj)` waits for read readiness
- `await task.wait_writable(obj)` waits for write readiness
- `await task.join(target)` and `join_all(targets)` wait for task completion
- adapter `.call(...)` methods route foreign execution through the runtime

Awaiting an arbitrary asyncio future produces `UnsupportedAwaitableError`.

## Cancellation

Request scheduler-owned cancellation through the runtime:

```python
status = runtime.cancel_task(task_or_pid, recursive=False)
```

The method returns `0` when the target was cancelled and `-1` when it cannot be
resolved. `recursive=True` cancels currently registered descendants first.
Cancellation is terminal and stored as `TaskCancelledError`; a parent awaiting
that task receives the same failure.

Cancellation does not automatically cancel sibling tasks or unrelated work.
For thread and asyncio adapter limitations, see
[Execution adapters](execution-adapters.md#lifecycle-and-cancellation).

## Watcher tasks and runtime exit

Watcher tasks represent background facilities such as an interactive shell or
metrics loop. With the default `eternal_watchers=False`, the runtime exits when
only watchers remain. Set `eternal_watchers=True` when watcher-only work should
keep the scheduler alive, and arrange an explicit cancellation or shutdown
path.
