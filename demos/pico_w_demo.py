"""
Raspberry Pi Pico W oriented demo entry point.

The Pico W profile exposes optional country and power-management defaults in
addition to the shared MicroPython socket/timer APIs.
"""

from common import build_runtime, default_tasks

from SmallPackage.Kernel import PicoW


WIFI_SSID = None
WIFI_PASSWORD = None
WIFI_COUNTRY = "US"
WIFI_HOSTNAME = "smallos-pico"
WIFI_POWER_MANAGEMENT = None


def maybe_connect_wifi(kernel):
    """Connect only when credentials are filled in for the target board."""
    if WIFI_SSID and WIFI_PASSWORD:
        kernel.connect_wifi(WIFI_SSID, WIFI_PASSWORD)


def main():
    # Country and power-management settings are profile options because their
    # implementation is firmware/board specific, not scheduler policy.
    kernel = PicoW(
        country=WIFI_COUNTRY,
        hostname=WIFI_HOSTNAME,
        power_management=WIFI_POWER_MANAGEMENT,
    )
    # Keep real credentials outside source control in an application deployment.
    maybe_connect_wifi(kernel)

    runtime = build_runtime(kernel)
    runtime.fork(default_tasks(kernel.board_name))
    runtime.startOS()


if __name__ == "__main__":
    main()
