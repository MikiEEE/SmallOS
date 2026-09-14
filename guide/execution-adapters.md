# Execution Adapters

[Previous: Kernels and MicroPython](kernels-and-micropython.md) ·
[Guide home](README.md) · [Next: Networking clients](networking-clients.md)

Execution adapters let a smallOS task yield while user-supplied code runs under
a different execution model. They use the standard library and do not install,
configure, or wrap database drivers, ORMs, SDKs, or other packages.

## Synchronous blocking code

Use `ThreadAdapter` for a blocking callable:

```python
from SmallPackage import SmallTask
from SmallPackage.adapters.threads import ThreadAdapter


def load_record(user_library, settings, record_id):
    connection = user_library.connect(**settings)
    try:
        return connection.load(record_id)
    finally:
        connection.close()


with ThreadAdapter(max_workers=4, max_pending=64) as blocking:
    async def load(task):
        return await blocking.call(
            load_record,
            user_selected_library,
            connection_settings,
            42,
        )

    runtime.fork(SmallTask(2, load, name="load"))
    runtime.start()
```

Use `max_workers=1` when a connection or session must remain on one serialized,
thread-affine lane. Create, use, and close that resource through calls on the
same adapter.

## Asyncio-owned code

`AsyncioAdapter` owns one persistent event loop on a dedicated thread, so
loop-affine resources can be reused when all operations use the same adapter:

```python
from SmallPackage import SmallTask
from SmallPackage.adapters.asyncio_loop import AsyncioAdapter


async def fetch_record(user_library, settings, record_id):
    async with user_library.Client(**settings) as client:
        return await client.fetch(record_id)


with AsyncioAdapter(max_pending=64) as foreign_async:
    async def load(task):
        return await foreign_async.call(
            fetch_record,
            user_selected_async_library,
            connection_settings,
            42,
        )

    runtime.fork(SmallTask(2, load, name="load"))
    runtime.start()
```

Pass an async callable to `call()`, not an asyncio `Task` or `Future` already
owned by another loop.

## Lifecycle and cancellation

- An adapter binds to the first smallOS runtime that uses it.
- Shutdown is explicit; wrap `runtime.start()` in the context manager.
- `max_pending` rejects excess work with `AdapterCapacityError` rather than
  blocking the scheduler.
- Cancelling a smallOS task can cancel queued thread work but cannot forcibly
  stop a running Python thread.
- Asyncio cancellation is requested on the adapter loop, but foreign code may
  delay or suppress it.
- `AsyncioAdapter.shutdown_error` records an unexpected loop stop or teardown
  failure; normal shutdown leaves it as `None`.

## Standard-library examples

These demos require nothing beyond smallOS:

```bash
python demos/adapters_demo.py
python demos/adapters_sqlite_demo.py
python demos/adapters_asyncio_demo.py
```

The SQLite demo owns its connection on one thread worker. The asyncio demo
reuses a queue, futures, and a background task on the persistent adapter loop.
