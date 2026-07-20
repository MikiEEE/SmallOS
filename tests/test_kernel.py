import sys
import socket
import unittest

sys.path.append("..")

from SmallPackage.Kernel import ESP32, ESP8266, MicroPythonKernel, PicoW, RaspberryPiPicoW, Unix, build_micropython_kernel


class FakeNIC:
    def __init__(self):
        self.active_calls = []
        self.connect_calls = []
        self.config_calls = []
        self.connected = False

    def active(self, flag):
        self.active_calls.append(flag)

    def isconnected(self):
        return self.connected

    def connect(self, ssid, password):
        self.connect_calls.append((ssid, password))
        self.connected = True

    def config(self, **kwargs):
        self.config_calls.append(kwargs)


class FakeNetworkModule:
    STA_IF = object()

    def __init__(self, nic):
        self.nic = nic
        self.hostname_calls = []
        self.wlan_modes = []

    def WLAN(self, mode):
        self.wlan_modes.append(mode)
        return self.nic

    def hostname(self, value):
        self.hostname_calls.append(value)


class FakeRP2Module:
    def __init__(self):
        self.country_calls = []

    def country(self, value):
        self.country_calls.append(value)


class FakePollObject:
    def __init__(self, fd):
        self.fd = fd

    def fileno(self):
        return self.fd


class FakePoller:
    def __init__(self, events):
        self.events = events
        self.registrations = []

    def register(self, obj, mask):
        self.registrations.append((obj, mask))

    def poll(self, timeout):
        return list(self.events)


class FakeSelectorKey:
    def __init__(self, fileobj, fd, events, data):
        self.fileobj = fileobj
        self.fd = fd
        self.events = events
        self.data = data


class CountingSelector:
    def __init__(self):
        self.keys = {}
        self.events = []
        self.registrations = []
        self.modifications = []
        self.unregistrations = []
        self.timeouts = []
        self.closed = False

    def register(self, obj, events, data=None):
        fd = obj if isinstance(obj, int) else obj.fileno()
        key = FakeSelectorKey(obj, fd, events, data)
        self.keys[fd] = key
        self.registrations.append((obj, events, data))
        return key

    def modify(self, obj, events, data=None):
        fd = obj if isinstance(obj, int) else obj.fileno()
        previous = self.keys[fd]
        key = FakeSelectorKey(previous.fileobj, fd, events, data)
        self.keys[fd] = key
        self.modifications.append((obj, events, data))
        return key

    def unregister(self, obj):
        fd = obj if isinstance(obj, int) else obj.fileno()
        self.unregistrations.append(fd)
        return self.keys.pop(fd)

    def select(self, timeout=None):
        self.timeouts.append(timeout)
        return [(self.keys[fd], mask) for fd, mask in self.events]

    def close(self):
        self.closed = True


class PersistentFakePoller:
    def __init__(self, use_ipoll=True):
        self.events = []
        self.registrations = []
        self.modifications = []
        self.unregistrations = []
        self.ipoll_timeouts = []
        self.poll_timeouts = []
        self.closed = False
        if not use_ipoll:
            self.ipoll = None

    def register(self, obj, mask):
        self.registrations.append((obj, mask))

    def modify(self, obj, mask):
        self.modifications.append((obj, mask))

    def unregister(self, obj):
        self.unregistrations.append(obj)

    def ipoll(self, timeout):
        self.ipoll_timeouts.append(timeout)
        return iter(self.events)

    def poll(self, timeout):
        self.poll_timeouts.append(timeout)
        return list(self.events)

    def close(self):
        self.closed = True


class FakeSelectModule:
    POLLIN = 0x001
    POLLOUT = 0x004
    POLLERR = 0x008
    POLLHUP = 0x010
    POLLNVAL = 0x020

    def __init__(self, poller=None):
        self.poller = poller
        self.poll_calls = 0

    def poll(self):
        self.poll_calls += 1
        return self.poller


class FakeSelectWithoutPoll:
    POLLIN = 0x001
    POLLOUT = 0x004


class TestKernelProfiles(unittest.TestCase):
    def test_build_micropython_kernel_detects_esp32_profile(self):
        kernel = build_micropython_kernel(machine_name="ESP32 module with ESP32")

        self.assertIsInstance(kernel, ESP32)
        self.assertEqual("ESP32", kernel.board_name)

    def test_build_micropython_kernel_detects_pico_w_profile(self):
        kernel = build_micropython_kernel(machine_name="Raspberry Pi Pico W with RP2040")

        self.assertIsInstance(kernel, PicoW)
        self.assertEqual("Raspberry Pi Pico W", kernel.board_name)

    def test_build_micropython_kernel_falls_back_to_generic_profile(self):
        kernel = build_micropython_kernel(machine_name="PYBD-SF2")

        self.assertIsInstance(kernel, MicroPythonKernel)
        self.assertNotIsInstance(kernel, ESP32)
        self.assertNotIsInstance(kernel, PicoW)

    def test_esp8266_profile_is_still_available(self):
        kernel = build_micropython_kernel(machine_name="ESP8266 board")

        self.assertIsInstance(kernel, ESP8266)
        self.assertEqual("ESP8266", kernel.board_name)

    def test_pico_w_alias_points_to_same_profile(self):
        self.assertIs(RaspberryPiPicoW, PicoW)

    def test_esp32_connect_wifi_applies_hostname(self):
        nic = FakeNIC()
        network_mod = FakeNetworkModule(nic)
        kernel = ESP32(
            hostname="smallos-esp32",
            modules={"network": network_mod},
        )

        connected_nic = kernel.connect_wifi("ssid", "password")

        self.assertIs(connected_nic, nic)
        self.assertEqual([True], nic.active_calls)
        self.assertEqual([("ssid", "password")], nic.connect_calls)
        self.assertEqual(["smallos-esp32"], network_mod.hostname_calls)

    def test_pico_w_connect_wifi_applies_country_hostname_and_power_mode(self):
        nic = FakeNIC()
        network_mod = FakeNetworkModule(nic)
        rp2_mod = FakeRP2Module()
        kernel = PicoW(
            country="US",
            hostname="smallos-pico",
            power_management=0xA11140,
            modules={"network": network_mod, "rp2": rp2_mod},
        )

        connected_nic = kernel.connect_wifi("ssid", "password")

        self.assertIs(connected_nic, nic)
        self.assertEqual([True], nic.active_calls)
        self.assertEqual([("ssid", "password")], nic.connect_calls)
        self.assertEqual(["US"], rp2_mod.country_calls)
        self.assertEqual(["smallos-pico"], network_mod.hostname_calls)
        self.assertIn({"pm": 0xA11140}, nic.config_calls)

    def test_unix_io_wait_maps_poll_file_descriptors_back_to_objects(self):
        readable_obj = FakePollObject(11)
        writable_obj = FakePollObject(22)
        poller = FakePoller([(11, 0x001), (22, 0x004)])

        kernel = Unix()
        kernel._poll_factory = lambda: poller

        readable, writable = kernel.io_wait([readable_obj], [writable_obj], timeout_ms=5)

        self.assertEqual([readable_obj], readable)
        self.assertEqual([writable_obj], writable)

    def test_unix_wait_set_applies_only_registration_deltas(self):
        readable_obj = FakePollObject(11)
        selector = CountingSelector()
        kernel = Unix()
        kernel._selector_factory = lambda: selector
        wait_set = kernel.create_io_wait_set()

        wait_set.set_interest(readable_obj, True, False)
        wait_set.set_interest(readable_obj, True, False)
        wait_set.set_interest(readable_obj, True, True)
        selector.events = [(11, kernel._selector_read_mask | kernel._selector_write_mask)]
        readable, writable = wait_set.wait(timeout_ms=5)
        wait_set.set_interest(readable_obj, False, False)
        wait_set.close()

        self.assertEqual(1, len(selector.registrations))
        self.assertEqual(1, len(selector.modifications))
        self.assertEqual([11], selector.unregistrations)
        self.assertEqual([0.005], selector.timeouts)
        self.assertEqual([readable_obj], readable)
        self.assertEqual([readable_obj], writable)
        self.assertTrue(selector.closed)

    def test_unix_wait_set_does_not_reregister_stable_objects(self):
        selector = CountingSelector()
        kernel = Unix()
        kernel._selector_factory = lambda: selector
        wait_set = kernel.create_io_wait_set()
        io_objects = [FakePollObject(fd) for fd in range(100, 132)]
        try:
            for io_obj in io_objects:
                wait_set.set_interest(io_obj, True, False)
            for _ in range(100):
                wait_set.wait(timeout_ms=0)

            self.assertEqual(32, len(selector.registrations))
            self.assertEqual([], selector.modifications)
            self.assertEqual([], selector.unregistrations)
            self.assertEqual(100, len(selector.timeouts))
        finally:
            wait_set.close()

    def test_unix_wait_set_replaces_a_stale_descriptor_owner(self):
        selector = CountingSelector()
        kernel = Unix()
        kernel._selector_factory = lambda: selector
        wait_set = kernel.create_io_wait_set()
        original = FakePollObject(140)
        replacement = FakePollObject(140)
        try:
            wait_set.set_interest(original, True, False)
            original.fd = -1
            wait_set.set_interest(replacement, True, False)

            self.assertEqual(2, len(selector.registrations))
            self.assertEqual([140], selector.unregistrations)
            selector.events = [(140, kernel._selector_read_mask)]
            readable, _writable = wait_set.wait(timeout_ms=0)
            self.assertEqual([replacement], readable)
        finally:
            wait_set.close()

    def test_unix_wait_set_uses_real_socket_readiness_without_closing_socket(self):
        left, right = socket.socketpair()
        wait_set = Unix().create_io_wait_set()
        try:
            wait_set.set_interest(left, True, False)
            right.send(b"x")

            readable, writable = wait_set.wait(timeout_ms=100)
            self.assertEqual([left], readable)
            self.assertEqual([], writable)
        finally:
            wait_set.close()
            self.assertGreaterEqual(left.fileno(), 0)
            left.close()
            right.close()

    def test_unix_wait_set_reports_peer_hangup_as_readable(self):
        left, right = socket.socketpair()
        wait_set = Unix().create_io_wait_set()
        try:
            wait_set.set_interest(left, True, False)
            right.close()

            readable, _writable = wait_set.wait(timeout_ms=100)
            self.assertEqual([left], readable)
        finally:
            wait_set.close()
            left.close()

    def test_micropython_wait_set_reuses_poller_and_ipoll(self):
        poller = PersistentFakePoller()
        select_mod = FakeSelectModule(poller)
        kernel = MicroPythonKernel(modules={"select": select_mod})
        wait_set = kernel.create_io_wait_set()
        io_obj = FakePollObject(21)

        wait_set.set_interest(io_obj, True, False)
        wait_set.set_interest(io_obj, True, False)
        wait_set.set_interest(io_obj, True, True)
        poller.events = [(21, select_mod.POLLIN, "port-specific-extra")]
        readable, writable = wait_set.wait(timeout_ms=7)
        wait_set.set_interest(io_obj, False, False)
        wait_set.close()

        self.assertEqual(1, select_mod.poll_calls)
        self.assertEqual([(io_obj, select_mod.POLLIN)], poller.registrations)
        self.assertEqual(
            [(io_obj, select_mod.POLLIN | select_mod.POLLOUT)],
            poller.modifications,
        )
        self.assertEqual([io_obj], poller.unregistrations)
        self.assertEqual([7], poller.ipoll_timeouts)
        self.assertEqual([], poller.poll_timeouts)
        self.assertEqual([io_obj], readable)
        self.assertEqual([], writable)
        self.assertTrue(poller.closed)

    def test_micropython_wait_set_falls_back_to_poll_and_maps_errors(self):
        poller = PersistentFakePoller(use_ipoll=False)
        select_mod = FakeSelectModule(poller)
        kernel = MicroPythonKernel(modules={"select": select_mod})
        wait_set = kernel.create_io_wait_set()
        readable_obj = FakePollObject(31)
        writable_obj = FakePollObject(32)

        wait_set.set_interest(readable_obj, True, False)
        wait_set.set_interest(writable_obj, False, True)
        poller.events = [
            (31, select_mod.POLLHUP),
            (32, select_mod.POLLERR),
        ]

        readable, writable = wait_set.wait(timeout_ms=None)
        wait_set.close()

        self.assertEqual([readable_obj], readable)
        self.assertEqual([writable_obj], writable)
        self.assertEqual([-1], poller.poll_timeouts)

    def test_micropython_wait_set_detaches_invalid_event(self):
        poller = PersistentFakePoller()
        select_mod = FakeSelectModule(poller)
        kernel = MicroPythonKernel(modules={"select": select_mod})
        wait_set = kernel.create_io_wait_set()
        io_obj = FakePollObject(41)

        wait_set.set_interest(io_obj, True, True)
        poller.events = [(41, select_mod.POLLNVAL)]
        readable, writable = wait_set.wait(timeout_ms=0)
        poller.events = []
        second_readable, second_writable = wait_set.wait(timeout_ms=0)
        wait_set.close()

        self.assertEqual([io_obj], readable)
        self.assertEqual([io_obj], writable)
        self.assertEqual([], second_readable)
        self.assertEqual([], second_writable)
        self.assertEqual([io_obj], poller.unregistrations)

    def test_micropython_poll_wait_set_works_with_cpython_poll(self):
        kernel = MicroPythonKernel()
        if kernel._poll_factory is None:
            self.skipTest("host does not provide select.poll")
        left, right = socket.socketpair()
        wait_set = kernel.create_io_wait_set()
        try:
            wait_set.set_interest(left, True, False)
            right.send(b"x")

            readable, writable = wait_set.wait(timeout_ms=100)
            self.assertEqual([left], readable)
            self.assertEqual([], writable)
        finally:
            wait_set.close()
            left.close()
            right.close()

    def test_micropython_kernel_without_poll_keeps_snapshot_fallback(self):
        kernel = MicroPythonKernel(modules={"select": FakeSelectWithoutPoll()})

        self.assertIsNone(kernel.create_io_wait_set())


if __name__ == "__main__":
    unittest.main()
