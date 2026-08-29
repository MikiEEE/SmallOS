# Quick Start

[Previous: Installation](installation.md) · [Guide home](README.md) ·
[Next: Runtime concepts](runtime-concepts.md)

Create a task with an `async def` function, wrap it in `SmallTask`, and hand it
to a configured runtime:

```python
from SmallPackage import SmallOS, SmallOSConfig, SmallTask, Unix


async def hello(task):
    task.OS.print("hello from smallOS\n")
    await task.sleep(0.1)
    return "done"


config = SmallOSConfig.from_json_file("smallos.config.json")
runtime = SmallOS(config=config).setKernel(Unix())
runtime.setErrorHandler(
    lambda event: print(
        "[smallOS] task failure in {} (PID {}): {}".format(
            event["task_name"] or "unnamed task",
            event["task_id"],
            event["exception_repr"],
        )
    )
)
runtime.fork([SmallTask(2, hello, name="hello")])
runtime.startOS()
```

Save the example as `hello.py` in the repository root and run:

```bash
python hello.py
```

## What happens

1. `SmallOSConfig` loads task, priority, output, watcher, and client defaults.
2. `Unix` supplies desktop timing and I/O readiness behavior.
3. `SmallTask(2, ...)` creates a priority-2 task.
4. `fork(...)` registers it with the scheduler.
5. `startOS()` runs until no runnable work or configured eternal watcher remains.
6. `task.sleep(...)` yields control without using an asyncio event loop.

`start()` is also available as an alias for `startOS()`.

## Next steps

- Learn how scheduling and task-owned awaitables work in
  [Runtime concepts](runtime-concepts.md).
- Tune capacity and client defaults in [Configuration](configuration.md).
- Install a production-friendly observer using
  [Error handling](error-handling.md).
