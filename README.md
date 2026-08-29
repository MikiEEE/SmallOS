# smallOS

`smallOS` is a lightweight cooperative runtime for priority-oriented task
management. It keeps the familiar `async` / `await` syntax while letting
smallOS—not `asyncio`—own scheduling policy.

The project is experimental but usable. It currently provides priority-based
scheduling, task joins and signals, time and socket waits, desktop and
MicroPython kernels, execution adapters for blocking or asyncio-owned code,
and dependency-free HTTP, Redis, MQTT, SSE, and WebSocket clients.

## Why smallOS?

smallOS is designed for projects that need a small, explicit runtime surface:

- robotics and device-control experiments
- MicroPython and embedded exploration
- applications where task priority matters
- learning how coroutine schedulers work

Arbitrary asyncio libraries are not drop-in compatible because smallOS steps
its own coroutines. When an existing library owns blocking or asyncio work,
the runtime provides opt-in execution adapters.

## Quick start

smallOS supports CPython 3.10 and newer.

```bash
python3.10 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
python demos/unix_demo.py
```

Minimal runtime:

```python
from SmallPackage import SmallOS, SmallOSConfig, SmallTask, Unix


async def hello(task):
    task.OS.print("hello from smallOS\n")
    await task.sleep(0.1)
    return "done"


config = SmallOSConfig.from_json_file("smallos.config.json")
runtime = SmallOS(config=config).setKernel(Unix())
runtime.fork([SmallTask(2, hello, name="hello")])
runtime.startOS()
```

## Documentation

The [smallOS guide](guide/README.md) is the main documentation entry point.

- [Installation and validation](guide/installation.md)
- [Quick start](guide/quick-start.md)
- [Runtime concepts](guide/runtime-concepts.md)
- [Task lifecycle and coordination](guide/task-lifecycle.md)
- [Configuration](guide/configuration.md)
- [Core API reference](guide/api-reference.md)
- [Error handling and scheduler wakeups](guide/error-handling.md)
- [Kernels and MicroPython](guide/kernels-and-micropython.md)
- [Execution adapters](guide/execution-adapters.md)
- [Networking clients](guide/networking-clients.md)
- [Shell and TCP servers](guide/shell-and-server.md)
- [Demos](guide/demos.md)
- [Troubleshooting and limitations](guide/troubleshooting.md)
- [Contributing](guide/contributing.md)

## Project layout

- [`SmallPackage/`](SmallPackage): runtime package
- [`SmallPackage/clients/`](SmallPackage/clients): cooperative protocol clients
- [`SmallPackage/adapters/`](SmallPackage/adapters): blocking and asyncio bridges
- [`demos/`](demos): desktop and board examples
- [`tests/`](tests): unit, integration, and typing contracts

## License

smallOS is licensed under the [MIT License](LICENSE).
