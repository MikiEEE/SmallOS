# Kernels and MicroPython

[Previous: Error handling](error-handling.md) · [Guide home](README.md) ·
[Next: Execution adapters](execution-adapters.md)

Kernels isolate timing, output, socket, TLS, and readiness behavior from the
scheduler.

## Available profiles

Desktop:

- `Unix`

MicroPython:

- `MicroPythonKernel`
- `ESP32`
- `PicoW` / `RaspberryPiPicoW`
- `ESP8266` compatibility profile

Choose a profile directly or detect one from the firmware machine string:

```python
from SmallPackage import ESP32, PicoW, build_micropython_kernel

kernel = ESP32(hostname="smallos-esp32")
kernel = PicoW(country="US", hostname="smallos-pico")
kernel = build_micropython_kernel()
```

## MicroPython startup flow

1. Select `ESP32`, `PicoW`, or `build_micropython_kernel()`.
2. Optionally connect Wi-Fi through the kernel helper.
3. Create `SmallOS(config=...)` and attach the kernel.
4. Fork tasks and start the runtime.

See the [ESP32](../demos/esp32_demo.py),
[Pico W](../demos/pico_w_demo.py), and
[autodetection](../demos/micropython_autodetect_demo.py) demos.

## Portable networking boundary

Protocol clients should build on the shared TCP/TLS kernel surface instead of
requiring protocol-specific kernel methods.

Passive TCP consumers should:

1. check `supports_tcp_server()`
2. pass the opaque result from `resolve_passive_address()` unchanged to both
   `socket_open()` and `socket_bind()`
3. use kernel listen, accept, address-inspection, and close methods
4. check address-reuse support independently

Some MicroPython ports can listen without exposing `SO_REUSEADDR`. The
[web application demo](../demos/web_app_demo.py) shows complete setup and
rollback without importing platform socket APIs directly.

MicroPython support varies by firmware and board. Validate behavior on the
target hardware before depending on a kernel capability.
