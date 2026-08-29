# Installation and Validation

[Guide home](README.md) · [Next: Quick start](quick-start.md)

## Requirements

smallOS supports CPython 3.10 and newer. Python 3.6 through 3.9 are no longer
supported. MicroPython compatibility is maintained separately because its
language and standard-library support do not map directly to a CPython release.

The runtime has no third-party dependencies.

## Choose an installation path

> **Do not run `pip install SmallPackage`.** The normalized PyPI name
> `smallpackage` belongs to an unrelated project. smallOS currently publishes
> verified wheel and source archives through GitHub Releases, not PyPI.

### Install from a GitHub Release

Download the wheel for the desired version from the project's
[GitHub Releases](https://github.com/MikiEEE/SmallOS/releases), then install the
local file:

```bash
python -m pip install /path/to/smallpackage-VERSION-py3-none-any.whl
```

Confirm that the intended package is importable:

```bash
python -c "from SmallPackage import SmallOS, SmallTask, Unix; print('smallOS ready')"
```

The wheel is platform-independent Python code, but execution adapters require
desktop CPython facilities such as threads, sockets, and asyncio.

### Install from a source checkout

For a runtime-only editable install:

```bash
git clone https://github.com/MikiEEE/SmallOS.git
cd SmallOS
python3.10 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

### Development install

Install the development tools when you plan to change or validate smallOS:

```bash
python3.10 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

The `dev` extra installs the build, coverage, and Pyright tools used by the
repository. Run these commands from the repository root.

## Deploy to MicroPython

MicroPython boards do not generally consume CPython wheels. Deploy the source
package with the file-transfer or frozen-module workflow supported by your
firmware and board tooling:

1. Install a recent firmware build for the target board.
2. Copy `SmallPackage/` to the board filesystem or freeze it into the firmware.
3. Do not import `SmallPackage.adapters` on MicroPython; those backends require
   CPython threads and asyncio.
4. Copy the selected application or demo plus any configuration it loads.
5. Select `ESP32`, `PicoW`, or `build_micropython_kernel()` in the entry point.
6. Verify timer, socket, DNS, polling, Wi-Fi, and TLS behavior on the exact
   firmware build before deployment.

The board demos import `common.py`, which loads the repository-level
`smallos.config.json`. For a standalone board application, either deploy those
files alongside the demo or construct `SmallOSConfig` directly in application
code.

### Current board-support status

| Profile | Intended environment | Important validation |
| --- | --- | --- |
| `Unix` | CPython 3.10+ | Unit-tested in CI on Python 3.10–3.13 |
| `ESP32` | MicroPython with `network.WLAN` | Wi-Fi, polling, DNS, sockets, and TLS on target firmware |
| `PicoW` | Pico W MicroPython | Country/power settings, Wi-Fi, polling, sockets, and TLS |
| `ESP8266` | Compatible MicroPython ports | Memory limits and all network capabilities |
| `MicroPythonKernel` | Custom/constrained ports | Every capability used by the application |

The repository does not yet claim a versioned hardware/firmware certification
matrix. Record the board model and firmware version alongside application test
results.

## Validate the checkout

Run the unit tests:

```bash
python -m unittest discover -s tests -v
```

Run the same branch-coverage threshold used by CI:

```bash
coverage run -m unittest discover -s tests -v
coverage report
```

Run static analysis and build the distributions:

```bash
pyright
python -m build
```

GitHub Actions runs Pyright, unit tests on CPython 3.10 through 3.13, branch
coverage with a 60% floor, and distribution verification. Packaging begins
only after the earlier gates pass; CI installs the built wheel and smoke-tests
it outside the source checkout.

The package includes a `py.typed` marker. Type coverage is being expanded by
subsystem, so a clean Pyright run represents the configured boundary rather
than a claim that every legacy module is strictly typed.

## Run a demo

After installation, verify the desktop scheduler:

```bash
python demos/unix_demo.py
```

Continue with the [quick start](quick-start.md), or browse all available
[demos](demos.md).
