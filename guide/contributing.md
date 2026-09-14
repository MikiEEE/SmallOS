# Contributing

[Previous: Troubleshooting](troubleshooting.md) · [Guide home](README.md)

Contributions, issues, experiments, and board-port notes are welcome. Useful
areas include:

- validating MicroPython ports on real boards
- protocol clients built on the portable transport layer
- shell and debugging tools
- board demos and deployment examples
- scheduler tests and edge-case coverage
- documentation corrections and examples

## Development checks

Install the development dependencies as described in
[Installation](installation.md), then run checks proportional to the change:

```bash
python -m unittest discover -s tests -v
coverage run -m unittest discover -s tests -v
coverage report
pyright
python -m build
```

The CI pipeline tests CPython 3.10 through 3.13 and verifies distributions.
When changing core abstractions, account for both desktop CPython and
MicroPython-oriented imports and demos.

## Repository map

- [`SmallPackage/SmallOS.py`](../SmallPackage/SmallOS.py): scheduler
- [`SmallPackage/SmallTask.py`](../SmallPackage/SmallTask.py): coroutine stepping and joins
- [`SmallPackage/Kernel.py`](../SmallPackage/Kernel.py): platform kernels
- [`SmallPackage/SmallIO.py`](../SmallPackage/SmallIO.py): output routing
- [`SmallPackage/SmallConfig.py`](../SmallPackage/SmallConfig.py): runtime configuration
- [`SmallPackage/clients/`](../SmallPackage/clients): protocol clients
- [`SmallPackage/adapters/`](../SmallPackage/adapters): foreign execution bridges
- [`demos/`](../demos): examples
- [`tests/`](../tests): test suite

smallOS is licensed under the [MIT License](../LICENSE).
