# Core API Reference

[Previous: Configuration](configuration.md) · [Guide home](README.md) ·
[Next: Error handling](error-handling.md)

This page summarizes the public application-facing surface. Internal queue,
resume, completion, and registration methods are scheduler implementation
details even when Python does not enforce privacy.

## `SmallOS`

### Construction

```python
SmallOS(size=None, config=None, **overrides)
```

- `config` accepts `SmallOSConfig`, a compatible dictionary, or `None`.
- `size` overrides `task_capacity` for compatibility.
- `priority_levels`, `io_buffer_length`, and `eternal_watchers` may be passed as
  constructor overrides.

### Application methods

| Method | Result | Purpose |
| --- | --- | --- |
| `setKernel(kernel)` | runtime | Attach timing, output, and I/O primitives. |
| `fork(task)` | PID | Register one top-level task. |
| `fork([tasks])` | list of PIDs | Register tasks in input order. |
| `start()` | `None` | Run until no live work remains under watcher policy. |
| `startOS()` | `None` | Compatibility alias for `start()`. |
| `setErrorHandler(handler, include_cancelled=False)` | runtime | Observe finalized task failures. |
| `setEternalWatchers(enabled)` | runtime | Change watcher-only exit behavior. |
| `cancel_task(task_or_pid, recursive=False)` | `0` or `-1` | Cancel a registered task. |
| `print(...)` | `None` | Write application output through `SmallIO`. |

## `SmallTask`

### Construction

```python
SmallTask(priority, routine, name="", args=(), isReady=1, isWatcher=False)
```

The routine receives the task object first. `args` may be positional, keyword,
or a single extra value as described in [Task lifecycle](task-lifecycle.md).

### Properties and methods

| Member | Purpose |
| --- | --- |
| `done` | Whether the task reached a terminal state. |
| `result` | Stored successful result, otherwise `None`. |
| `exception` | Stored terminal exception, otherwise `None`. |
| `getID()` | Return the assigned PID (`-1` before registration). |
| `spawn(routine_or_task, priority=None, **kwargs)` | Register and return a child task. |
| `join(child)` | Return an awaitable for one child result. |
| `join_all(children)` | Return an awaitable for ordered results. |
| `sleep(seconds)` | Cooperatively wait for time. |
| `yield_now()` | Return to the ready queue. |
| `wait_signal(sig)` | Wait for signal slot `0`–`31`. |
| `sendSignal(pid, sig)` | Deliver a signal through the owning runtime. |
| `wait_readable(obj)` | Wait for kernel read readiness. |
| `wait_writable(obj)` | Wait for kernel write readiness. |
| `getSignals()` | List currently latched signal numbers. |

Prefer `runtime.cancel_task(...)` over direct lifecycle mutation methods so the
scheduler can remove wait registrations and notify joiners consistently.

## `SmallOSConfig`

| Method | Purpose |
| --- | --- |
| `SmallOSConfig.default()` | Return a fresh default configuration. |
| `from_dict(data)` | Load canonical fields and supported aliases. |
| `from_json_file(path)` | Load JSON using `json` or `ujson`. |
| `copy(**updates)` | Create an updated independent configuration. |
| `to_dict()` | Produce plain serializable data. |
| `client_defaults_for(section)` | Merge stream defaults with one client section. |

See [Configuration](configuration.md) for fields and defaults.

## Kernels

Application code normally selects a built-in kernel and uses task awaitables
rather than calling low-level socket methods directly:

```python
runtime.setKernel(Unix())
```

Portable components should check optional capabilities before use:

- `supports_tcp_server()` for passive listeners
- `supports_reuse_address()` for listener address reuse
- `supports_wakeup_channel()` for cross-thread scheduler notifications
- `supports_external_wait_objects()` before execution adapters depend on
  readiness objects

The [kernel guide](kernels-and-micropython.md) explains profiles and the
[shell/server guide](shell-and-server.md) shows the passive TCP sequence.

## Execution adapters and clients

Adapters and protocol clients have larger, subsystem-specific APIs:

- [Execution adapters](execution-adapters.md)
- [Networking clients](networking-clients.md)
- [Detailed client reference](../SmallPackage/clients/README.md)

## Exceptions

Common application-visible failures include:

- `TaskCancelledError`: scheduler-owned cancellation
- `UnsupportedAwaitableError`: an awaited object is not a smallOS instruction
- `MaxProcessError`: capacity or task registration failed
- `AdapterCapacityError`: adapter `max_pending` was reached
- protocol-specific client errors exported from `SmallPackage`

Install a runtime [error handler](error-handling.md) so failures in unjoined
top-level tasks remain visible.
