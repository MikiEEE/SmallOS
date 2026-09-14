# Shell and TCP Servers

[Previous: Networking clients](networking-clients.md) · [Guide home](README.md) ·
[Next: Demos](demos.md)

## Attach an interactive shell

`BaseShell` runs its input loop as a normal smallOS task. This keeps runtime
inspection cooperative instead of blocking the scheduler on `input()`:

```python
from SmallPackage import SmallOS, SmallTask, Unix
from SmallPackage.shells import BaseShell

runtime = SmallOS().setKernel(Unix())
shell = BaseShell(prompt="app> ", allow_python=False).setOS(runtime)
runtime.shells.append(shell)

shell_task = shell.make_task(
    priority=3,
    is_watcher=True,
    poll_interval=0.1,
)
runtime.fork([shell_task, SmallTask(2, application, name="application")])
runtime.start()
```

Use `allow_python=False` whenever shell input is not fully trusted. The Python
command evaluates arbitrary code in the process when enabled.

### Built-in commands

| Command | Purpose |
| --- | --- |
| `help [command]` | Show command help and aliases. |
| `ps` | List registered tasks. |
| `stat [pid]` | Show runtime or detailed task state. |
| `count` | Show task and watcher counts. |
| `children <pid>` | List a task's known children. |
| `signal <pid> <sig>` | Deliver an application signal. |
| `signals <pid>` | Inspect latched signals. |
| `kill <pid> [-r]` | Cancel one task or its descendants. |
| `toggle` | Switch between shell and application output views. |
| `io [status\|show\|flush\|clear]` | Inspect buffered application output. |
| `echo <text>` | Write through the shell channel. |
| `python <code>` | Evaluate code when explicitly enabled. |
| `exit` | End the shell task, not the whole process. |

See [`demos/shell_demo.py`](../demos/shell_demo.py) for a deterministic scripted
session and [`demos/web_app_demo.py`](../demos/web_app_demo.py) for an
interactive shell beside a server.

## Build a passive TCP server

Keep platform socket details behind the kernel. A portable listener follows
this order:

```python
kernel = task.OS.kernel
if not kernel.supports_tcp_server():
    raise NotImplementedError("passive TCP is unavailable")

address = kernel.resolve_passive_address(host, port)
listener = kernel.socket_open(address)
try:
    if kernel.supports_reuse_address():
        kernel.socket_set_reuse_address(listener, True)
    kernel.socket_bind(listener, address)
    kernel.socket_listen(listener, backlog)
    kernel.socket_setblocking(listener, False)

    while True:
        try:
            client, client_address = kernel.socket_accept(listener)
        except Exception as exc:
            retry = kernel.socket_retry_mode(exc, "accept")
            if retry == "read":
                await task.wait_readable(listener)
                continue
            if retry == "write":
                await task.wait_writable(listener)
                continue
            raise

        try:
            kernel.socket_setblocking(client, False)
            task.spawn(handle_client, args=(client, client_address))
        except BaseException:
            # The accept loop still owns the stream until spawn succeeds.
            kernel.socket_close(client)
            raise
        await task.yield_now()
finally:
    kernel.socket_close(listener)
```

The address returned by `resolve_passive_address()` is opaque: pass it
unchanged to `socket_open()` and `socket_bind()`. Treat address reuse as a
separate capability because some MicroPython ports support listening without
exposing reuse constants.

## Connection ownership

After accepting a client, exactly one task should own and close that socket.
If handler creation fails, close the socket in the accept path. Once the child
is registered successfully, its `finally` block should close it. This avoids
both descriptor leaks and double-close races.

Socket calls must classify retry behavior with
`kernel.socket_retry_mode(error, operation)`. Wait for the mode it reports;
do not assume every would-block condition waits for readability.

The web app demo implements bounded request headers, per-client handler tasks,
setup rollback, routing, metrics, shell cancellation, and listener cleanup.
It is educational code rather than a production HTTP server: add timeouts,
request-body handling, concurrency limits, authentication, and security review
for a real service.
