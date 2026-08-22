# smallOS

`smallOS` is a lightweight cooperative runtime for priority-oriented task
management.

It is designed around three ideas:
- write tasks with modern `async` / `await` syntax
- keep scheduling policy owned by `smallOS`, not `asyncio`
- stay portable enough to run on desktop Python today and MicroPython boards
  later

## Status

The project is currently experimental but usable. The runtime core supports:
- priority-based cooperative scheduling
- task spawning, `join`, and `join_all`
- signal-based wakeups
- time-based sleeping
- readiness-based socket/I/O waiting
- generic TCP/TLS kernel hooks for higher-level protocols
- dependency-free thread and asyncio execution adapters for user libraries
- smallOS-native HTTP, Redis, MQTT, SSE, and WebSocket helper clients

## Why smallOS?

Python's `asyncio` gives great syntax, but it also brings its own scheduler and
event-loop policy. `smallOS` keeps the syntax while swapping in a custom
runtime, so tasks can be scheduled with project-specific priority rules and a
smaller portability surface.

That makes it a good fit for:
- robotics or device-control projects
- embedded experiments on MicroPython boards
- custom runtimes where task priority matters
- learning how coroutine scheduling works under the hood

## Project Layout

- [SmallPackage/SmallOS.py](SmallPackage/SmallOS.py):
  cooperative scheduler
- [SmallPackage/SmallTask.py](SmallPackage/SmallTask.py):
  task lifecycle, coroutine stepping, join bookkeeping
- [SmallPackage/Kernel.py](SmallPackage/Kernel.py):
  desktop and MicroPython kernel abstractions
- [SmallPackage/SmallIO.py](SmallPackage/SmallIO.py):
  buffered app/shell output routing and terminal-mode helpers
- [SmallPackage/clients](SmallPackage/clients):
  protocol client package for cooperative network integrations
- [SmallPackage/adapters](SmallPackage/adapters):
  dependency-free escape hatches for blocking and asyncio-owned user code
- [SmallPackage/clients/README.md](SmallPackage/clients/README.md):
  detailed client-specific guide and API notes
- [SmallPackage/clients/SmallHTTP.py](SmallPackage/clients/SmallHTTP.py):
  dependency-free HTTP and SSE clients for smallOS tasks
- [SmallPackage/clients/SmallStream.py](SmallPackage/clients/SmallStream.py):
  cooperative socket stream helper for protocol clients
- [SmallPackage/clients/SmallRedis.py](SmallPackage/clients/SmallRedis.py):
  dependency-free Redis client for smallOS tasks
- [SmallPackage/clients/SmallMQTT.py](SmallPackage/clients/SmallMQTT.py):
  dependency-free MQTT client for smallOS tasks
- [SmallPackage/clients/SmallWebSocket.py](SmallPackage/clients/SmallWebSocket.py):
  dependency-free WebSocket client for bidirectional messaging
- [SmallPackage/SmallConfig.py](SmallPackage/SmallConfig.py):
  runtime configuration loader/container
- [smallos.config.json](smallos.config.json):
  repo-level runtime defaults
- [SmallPackage/shells.py](SmallPackage/shells.py):
  command shell helpers for runtime inspection and demos
- [demos](demos):
  desktop and board-specific demo entry points
- [tests](tests):
  unit tests for scheduler, kernel, config, and supporting structures

## Installation

Desktop development:

```bash
python3.10 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

smallOS supports CPython 3.10 and newer. Python 3.6 through 3.9 are no
longer supported. MicroPython compatibility is maintained separately because
its language and standard-library support do not map directly to a CPython
release number; checker-only imports are kept off embedded runtime paths.

Run the test suite:

```bash
python3 -m unittest discover -s tests -v
```

Run the tests with the same branch-coverage gate used by CI:

```bash
coverage run -m unittest discover -s tests -v
coverage report
```

Run the static type checker:

```bash
pyright
```

Build the wheel and source distribution:

```bash
python -m build
```

The GitHub Actions pipeline runs four gates: Pyright, unit tests across Python
3.10–3.13, branch coverage with a 60% floor, and distribution verification.
Packaging runs only after the earlier gates pass, installs the built wheel,
and smoke-tests it outside the source checkout.

The package ships a `py.typed` marker. Type coverage is being tightened by
subsystem: configuration, awaitables, task lifecycle, scheduling, signals,
platform kernels, and core utilities form the current checked boundary, while
protocol clients, shells, and demos remain on the incremental typing backlog.

## Quick Start

Minimal desktop runtime:

```python
from SmallPackage.Kernel import Unix
from SmallPackage.SmallConfig import SmallOSConfig
from SmallPackage.SmallOS import SmallOS
from SmallPackage.SmallTask import SmallTask


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

## Runtime Error Handling

`smallOS` now supports a runtime-level error observer through
`runtime.setErrorHandler(handler, include_cancelled=False)`.

Use it when you want:
- readable debug output for uncaught task failures
- lightweight cleanup or bookkeeping at the runtime boundary
- a single place to surface task errors without crashing the scheduler

The handler is synchronous and receives a failure-event dictionary after the
task has been finalized. Current event fields include:
- `task_id`
- `task_name`
- `parent_id`
- `exception`
- `exception_type`
- `exception_repr`
- `is_cancelled`
- `blocked_reason`
- `waiting_signal`
- `io_wait_mode`
- `join_target_id`
- `join_pending_ids`
- `adapter_name`
- `adapter_job_id`
- `traceback_text`

By default, `TaskCancelledError` does not trigger the handler. Pass
`include_cancelled=True` if you want cancellation events too.

Example:

```python
from SmallPackage.Kernel import Unix
from SmallPackage.SmallOS import SmallOS


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

### Closed or Invalid File Descriptors

Closed or invalid file descriptors used in `wait_readable(...)` or
`wait_writable(...)` no longer crash the whole scheduler through the platform
poll/select layer.

Instead:
- the kernel validates the watched object before polling
- the waiting task receives a normal exception such as `ValueError`
- the runtime finalizes that task cleanly
- your runtime error handler can log or clean up the failure gracefully

If you do not install an error handler, the task still fails cleanly and the
runtime keeps its internal state consistent, but adding `setErrorHandler(...)`
is the recommended way to make these failures visible in applications.

### Waking a Blocked Scheduler from Another Thread

Kernels may provide an opaque wakeup channel for code that must request work
such as server shutdown while the scheduler is blocked in I/O readiness:

```python
kernel = Unix()
if not kernel.supports_wakeup_channel():
    raise RuntimeError("cross-thread scheduler wakeup is unavailable")

wakeup = kernel.create_wakeup_channel()

async def watch_shutdown(task):
    await task.wait_readable(wakeup.wait_object)
    wakeup.drain()
    # Apply the application-owned shutdown request on the scheduler thread.
```

Call `wakeup.notify()` from the external thread. Notifications are nonblocking
and coalesce until the scheduler calls `drain()`. The owner must call `close()`
after its scheduler wait has been detached; repeated close, notify, and drain
calls during teardown are safe.

`Unix` supports this contract when its socket module provides a callable
`socketpair()`. Generic `MicroPythonKernel` deliberately reports it unsupported:
a polling backend or socket-pair-shaped attribute alone does not establish safe
cross-thread behavior on a constrained port. TCP serving and shutdown initiated
by a task already running on the scheduler do not require this capability.

## Configuration

The runtime now uses a first-class config object backed by
[smallos.config.json](smallos.config.json).

Current config fields:
- `task_capacity`: maximum tracked tasks / PID slots
- `priority_levels`: number of ready-queue categories
- `io_buffer_length`: buffered app output length when the terminal view is hidden
- `eternal_watchers`: keep the runtime alive when only watcher tasks remain
- `client_defaults`: shared defaults for cooperative clients and streams

Example:

```json
{
  "task_capacity": 1024,
  "priority_levels": 10,
  "io_buffer_length": 1024,
  "eternal_watchers": false,
  "client_defaults": {
    "stream": {
      "max_buffer_size": 16777216
    },
    "http": {
      "max_response_size": 16777216
    },
    "redis": {
      "max_response_size": 16777216,
      "max_nesting_depth": 32
    },
    "mqtt": {
      "keepalive": 60,
      "max_packet_size": 262144,
      "max_queued_messages": 1024
    }
  }
}
```

The config loader also accepts the aliases `oslist_length` and
`num_categories` so older notes and experiments can map cleanly onto the
current runtime.

Client constructors still accept explicit overrides, but when you create them
inside a task they now inherit these defaults from `task.OS.config` unless you
pass a value directly.

## Kernels and Board Profiles

Desktop kernel:
- `Unix`

MicroPython kernels:
- `MicroPythonKernel`
- `ESP32`
- `PicoW` / `RaspberryPiPicoW`
- `ESP8266` compatibility profile

You can either pick a board profile explicitly or let the runtime choose a
built-in profile from the firmware machine string:

```python
from SmallPackage.Kernel import ESP32, PicoW, build_micropython_kernel

kernel = ESP32(hostname="smallos-esp32")
kernel = PicoW(country="US", hostname="smallos-pico")
kernel = build_micropython_kernel()
```

## Demos

The new demos live in [demos](demos):
- [demos/unix_demo.py](demos/unix_demo.py):
  desktop scheduler demo
- [demos/esp32_demo.py](demos/esp32_demo.py):
  ESP32-oriented startup and optional Wi-Fi bring-up example
- [demos/pico_w_demo.py](demos/pico_w_demo.py):
  Pico W oriented startup and Wi-Fi configuration example
- [demos/micropython_autodetect_demo.py](demos/micropython_autodetect_demo.py):
  automatic MicroPython kernel selection
- [demos/runtime_demo.py](demos/runtime_demo.py):
  migrated home for the original root-level runtime showcase
- [demos/shell_demo.py](demos/shell_demo.py):
  scripted shell session running alongside other cooperative tasks
- [demos/redis_demo.py](demos/redis_demo.py):
  Redis example built on the native cooperative client
- [demos/http_demo.py](demos/http_demo.py):
  HTTP example built on the native cooperative client
- [demos/web_app_demo.py](demos/web_app_demo.py):
  cooperative single-thread web app demo with HTTP routes, live browser UI, and shell-driven server shutdown
- [demos/mqtt_demo.py](demos/mqtt_demo.py):
  MQTT example built on the native cooperative client
- [demos/adapters_demo.py](demos/adapters_demo.py):
  thread and asyncio escape hatches running beside a regular SmallOS task
- [demos/adapters_sqlite_demo.py](demos/adapters_sqlite_demo.py):
  a user-owned `sqlite3` connection kept on one thread-adapter worker
- [demos/adapters_asyncio_demo.py](demos/adapters_asyncio_demo.py):
  a persistent asyncio queue and background task reused across adapter calls

All of the shared demo entry points now install a default runtime error handler
through [demos/common.py](demos/common.py). That means network failures,
invalid I/O wait objects, and other uncaught task exceptions are reported as
readable task-failure diagnostics instead of looking like abrupt scheduler
crashes or silent exits.

The original root demo remains available in
[demo.py](demo.py) as a compatibility wrapper around
[demos/runtime_demo.py](demos/runtime_demo.py).

## Runtime Model

`smallOS` is intentionally small in scope:
- tasks are `async def` coroutines wrapped in `SmallTask`
- task code awaits smallOS-owned awaitables such as `task.sleep(...)`,
  `task.wait_signal(...)`, `task.wait_readable(...)`, and `task.join(...)`
- the scheduler steps coroutines directly and decides when each task becomes
  runnable again
- kernels provide timing, output, and readiness-based transport primitives

This means arbitrary `asyncio` libraries are not drop-in compatible with the
runtime, but it also means scheduling policy and portability stay under your
control.

## Execution Adapters

Execution adapters let a SmallOS task yield while user-supplied code runs under
a different execution model. They use only the Python standard library and do
not install, import, configure, or wrap database drivers, ORMs, SDKs, or other
third-party packages.

Use `ThreadAdapter` for a synchronous blocking callable:

```python
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

Use `AsyncioAdapter` for an async callable that must run on asyncio. The
adapter owns one persistent event loop in a dedicated thread, allowing
loop-affine clients to be reused when all their operations are routed through
the same adapter:

```python
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

Important behavior:

- adapters bind to the first SmallOS runtime that uses them;
- adapter shutdown is explicit, so a context manager should wrap
  `runtime.start()`;
- `max_pending` rejects excess work with `AdapterCapacityError` instead of
  blocking the scheduler;
- cancelling a SmallTask can cancel queued thread work, but cannot forcibly
  stop a running Python thread;
- asyncio cancellation is requested on the adapter loop, but a user library
  may delay or suppress it;
- pass an async callable to `AsyncioAdapter.call()`, not a `Task` or `Future`
  already owned by another loop;
- inspect `AsyncioAdapter.shutdown_error` after shutdown when application
  diagnostics need to detect an unexpected loop stop or library teardown
  failure; normal shutdown leaves it as `None`;
- use `ThreadAdapter(max_workers=1)` when user resources require a serialized,
  thread-affine execution lane; create, use, and close those resources through
  calls on that same adapter rather than creating them on the SmallOS thread.

### Standard-library examples

All adapter demos run without installing anything beyond SmallOS:

```bash
python3 demos/adapters_demo.py
python3 demos/adapters_sqlite_demo.py
python3 demos/adapters_asyncio_demo.py
```

- [demos/adapters_demo.py](demos/adapters_demo.py) runs both adapters beside an
  ordinary cooperative SmallOS task.
- [demos/adapters_sqlite_demo.py](demos/adapters_sqlite_demo.py) creates, uses,
  and closes an in-memory `sqlite3` connection through
  `ThreadAdapter(max_workers=1)`. This is the ownership pattern to adapt for a
  thread-affine PostgreSQL driver or ORM session supplied by the user.
- [demos/adapters_asyncio_demo.py](demos/adapters_asyncio_demo.py) creates an
  `asyncio.Queue`, `Future` objects, and a background task, performs multiple
  operations, and cleans them up on the same persistent adapter event loop.

## Running on MicroPython

For MicroPython targets, the intended flow is:
1. choose `ESP32`, `PicoW`, or `build_micropython_kernel()`
2. optionally connect Wi-Fi through the kernel helper
3. build `SmallOS(config=...)`
4. fork tasks and start the runtime

The kernel layer is deliberately generic. Protocol clients such as HTTPS,
Redis, MQTT, RabbitMQ/AMQP, and Kafka should be built on top of the shared
TCP/TLS socket surface rather than requiring protocol-specific kernel methods.

Passive TCP consumers use the kernel boundary as well: check
`supports_tcp_server()` before resolving or opening anything, pass the opaque
record returned by `resolve_passive_address()` unchanged to both `socket_open()`
and `socket_bind()`, then use the kernel's listen, accept, address-inspection,
and close operations. Address reuse has its own capability check because some
MicroPython ports support listeners without exposing `SO_REUSEADDR` constants.
The web app demo shows the complete setup and rollback pattern without importing
platform socket APIs.

## Clients

The current setup now includes first-party smallOS-native helpers for HTTP,
Redis, and MQTT, so users can stay inside the smallOS scheduler instead of
dropping down to raw sockets or depending on `asyncio`-owned clients.

Available helpers:
- `SmallHTTPClient`
- `SmallRedisClient`
- `SmallMQTTClient`

Current scope:
- HTTP: request/response helper with query params, JSON bodies, TLS, and
  chunked/content-length response parsing
- Redis: RESP command execution plus helpers like `ping`, `get`, `set`,
  `delete`, `publish`, and `subscribe`
- MQTT: MQTT 3.1.1 connect/disconnect, publish at QoS 0/1/2, subscribe at
  QoS 0/1/2, and inbound message receive with PUBACK/PUBREC/PUBREL/PUBCOMP
  handling as required by the protocol
- Both clients: optional username/password auth and TLS transport setup, with
  Unix support for custom CA and client certificate paths through
  `tls_ca_file`, `tls_cert_file`, and `tls_key_file`

For detailed examples, constructor options, response helpers, and transport
notes, see
[SmallPackage/clients/README.md](SmallPackage/clients/README.md).

## Contributing

Contributions, issues, experiments, and board-port notes are welcome. Good
areas for contribution include:
- new MicroPython port validation
- higher-level protocol clients built on the transport layer
- shell and debugging tools
- more board demos and deployment examples
- additional scheduler tests and edge-case coverage

## License

This project is licensed under the MIT License. See
[LICENSE](LICENSE).
