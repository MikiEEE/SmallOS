# Runtime Concepts

[Previous: Quick start](quick-start.md) · [Guide home](README.md) ·
[Next: Task lifecycle](task-lifecycle.md)

## Runtime model

smallOS is a cooperative runtime:

- tasks are `async def` coroutines wrapped in `SmallTask`
- task code awaits smallOS-owned operations such as `task.sleep(...)`,
  `task.wait_signal(...)`, `task.wait_readable(...)`, and `task.join(...)`
- the scheduler steps coroutines directly and decides which priority becomes
  runnable next
- kernels provide time, output, networking, and readiness primitives

Work must yield cooperatively. CPU-heavy functions and blocking libraries
prevent the scheduler from making progress unless they are routed through an
[execution adapter](execution-adapters.md).

## Tasks and priority

The first `SmallTask` argument is its priority category:

```python
runtime.fork([
    SmallTask(1, control_loop, name="control"),
    SmallTask(5, telemetry_loop, name="telemetry"),
])
```

Priorities start at `1` and must be lower than the configured
`priority_levels`. Lower numbers run first; tasks at the same priority retain
FIFO behavior.

## Waiting without blocking

Use task methods to suspend until the runtime-owned condition is ready:

```python
async def worker(task):
    REFRESH_SIGNAL = 1
    await task.sleep(0.25)
    await task.wait_signal(REFRESH_SIGNAL)
    await task.wait_readable(socket_object)
```

Readiness objects and behavior depend on the active
[kernel](kernels-and-micropython.md).

## Child tasks and joins

Tasks can wait for one child with `task.join(child)` or multiple children with
`task.join_all(children)`. The scheduler retains the ownership and bookkeeping
needed to resume the parent when the requested work finishes.

See [`demos/runtime_demo.py`](../demos/runtime_demo.py) for a broader runtime
showcase.

The [task lifecycle guide](task-lifecycle.md) covers spawning, results,
exception propagation, cancellation, signals, and watchers in detail.

## Asyncio compatibility

smallOS uses Python coroutine syntax, but it does not run tasks on asyncio's
event loop. An arbitrary asyncio `Task`, `Future`, or library cannot be awaited
directly from a smallOS task. Route compatible callable factories through
`AsyncioAdapter`; use `ThreadAdapter` for synchronous blocking work.
