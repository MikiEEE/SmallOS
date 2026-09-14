# Troubleshooting and Limitations

[Previous: Demos](demos.md) · [Guide home](README.md) ·
[Next: Contributing](contributing.md)

Install a runtime [error handler](error-handling.md) first. Without one, a
failed detached task can look like it simply stopped producing output.

## Common problems

### `pip install SmallPackage` installs the wrong project

The PyPI name belongs to an unrelated maintainer. Remove that distribution and
install the verified smallOS wheel from GitHub Releases or use a source
checkout. Confirm the import path and project origin before deployment.

### The runtime exits while a background task remains

If every remaining task has `isWatcher=True` and `eternal_watchers` is false,
the scheduler exits intentionally. Set the configuration field to true only
when watcher-only work should keep the application alive, and provide an
explicit shutdown path.

### `runtime.fork(...)` raises `MaxProcessError`

The task capacity is exhausted, or the priority is invalid. Valid priorities
are `1` through `priority_levels - 1`. Increase `task_capacity`, correct the
priority, or ensure completed work is not being replaced faster than it can
finish.

### A task stalls the entire runtime

Cooperative tasks must yield. A long CPU loop, blocking socket call, `time.sleep`,
or synchronous SDK call prevents every smallOS task from progressing. Break CPU
work into bounded steps with `yield_now()` or route blocking libraries through
`ThreadAdapter`.

### `UnsupportedAwaitableError`

smallOS does not own arbitrary asyncio futures or coroutine scheduling. Use
smallOS task awaitables, or pass an async callable to `AsyncioAdapter.call()`.
Do not pass an asyncio `Task` or `Future` created on another loop.

### I/O waiting fails with `ValueError`

The watched object may be closed, invalid, or unsupported by the active kernel.
The runtime fails only the waiting task and reports the event to the configured
error handler. Keep socket close ownership explicit and detach/cancel waiting
tasks before closing shared descriptors.

### An adapter is unavailable

The kernel must support external readiness objects. `Unix` does; MicroPython
support depends on the polling backend. Also check that the adapter is open,
has not bound to a different runtime, and has free `max_pending` capacity.

### TLS works on desktop but not on a board

MicroPython TLS APIs and certificate behavior vary by firmware. Validate SNI,
CA loading, verification, memory use, and handshake retry behavior on the exact
board build. Do not assume desktop certificate-path options exist unchanged.

### Cross-thread shutdown does not wake the scheduler

Check `kernel.supports_wakeup_channel()` before creating a channel. Generic
MicroPython kernels report this unsupported. If the shutdown request originates
inside a smallOS task, apply it directly without a cross-thread channel.

### The shell appears to hide application output

The shell and application have separate views. Use `toggle` to switch views and
`io status`, `io show`, or `io flush` to inspect buffered output.

## Current limitations

- smallOS is experimental and its APIs may evolve.
- Task scheduling is cooperative; there is no preemption.
- Arbitrary asyncio libraries require `AsyncioAdapter`.
- Running Python threads cannot be forcibly stopped on task cancellation.
- MicroPython compatibility depends on board and firmware capabilities.
- PyPI publication is blocked by distribution-name ownership.
- The bundled web server is a teaching example, not a hardened HTTP stack.
- Type checking covers configured subsystems incrementally, not every legacy
  module at strict settings.

When reporting a problem, include Python or firmware version, board/OS, kernel
profile, configuration, minimal task code, full error-handler output, and
whether the problem reproduces with the closest demo.
