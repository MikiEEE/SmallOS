# Demos

[Previous: Shell and TCP servers](shell-and-server.md) · [Guide home](README.md) ·
[Next: Troubleshooting](troubleshooting.md)

The [`demos/`](../demos) directory contains focused runnable examples.

## Runtime and shells

- [`unix_demo.py`](../demos/unix_demo.py): desktop scheduler
- [`runtime_demo.py`](../demos/runtime_demo.py): broader runtime showcase
- [`shell_demo.py`](../demos/shell_demo.py): scripted shell beside cooperative tasks

The root [`demo.py`](../demo.py) remains a compatibility wrapper around the
runtime demo.

## Boards

- [`esp32_demo.py`](../demos/esp32_demo.py): ESP32 startup and optional Wi-Fi
- [`pico_w_demo.py`](../demos/pico_w_demo.py): Pico W startup and Wi-Fi
- [`micropython_autodetect_demo.py`](../demos/micropython_autodetect_demo.py):
  automatic kernel selection

## Networking

- [`http_demo.py`](../demos/http_demo.py): native HTTP client
- [`redis_demo.py`](../demos/redis_demo.py): native Redis client
- [`mqtt_demo.py`](../demos/mqtt_demo.py): native MQTT client
- [`web_app_demo.py`](../demos/web_app_demo.py): single-thread HTTP routes, live
  browser UI, and shell-driven shutdown

## Execution adapters

- [`adapters_demo.py`](../demos/adapters_demo.py): both adapters beside a smallOS task
- [`adapters_sqlite_demo.py`](../demos/adapters_sqlite_demo.py): thread-affine SQLite
- [`adapters_asyncio_demo.py`](../demos/adapters_asyncio_demo.py): persistent asyncio resources

Shared entry points install a default error handler through
[`demos/common.py`](../demos/common.py). Network failures, invalid I/O wait
objects, and other uncaught task exceptions therefore appear as readable task
diagnostics.

The demos contain inline comments explaining where control returns to the
scheduler, why resource ownership matters, and how kernel capability checks
keep the same application shape portable.
