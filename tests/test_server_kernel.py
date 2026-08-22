import asyncio
import os
import socket
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "demos"))

from demos.web_app_demo import _dispatch_client, _open_listener, web_server_task
from SmallPackage.Kernel import Kernel, MicroPythonKernel, Unix


class FakeStream:
    def __init__(self):
        self.blocking_calls = []
        self.option_calls = []
        self.bind_calls = []
        self.listen_calls = []
        self.accept_result = (object(), ("192.0.2.2", 5000))
        self.local_address = ("0.0.0.0", 8080)
        self.peer_address = ("192.0.2.2", 5000)
        self.peer_error = None
        self.close_calls = 0

    def setblocking(self, flag):
        self.blocking_calls.append(flag)

    def setsockopt(self, level, option, value):
        self.option_calls.append((level, option, value))

    def bind(self, address):
        self.bind_calls.append(address)

    def listen(self, backlog):
        self.listen_calls.append(backlog)

    def accept(self):
        return self.accept_result

    def getsockname(self):
        return self.local_address

    def getpeername(self):
        if self.peer_error is not None:
            raise self.peer_error
        return self.peer_address

    def send(self, data):
        return len(data)

    def recv(self, _size):
        return b""

    def close(self):
        self.close_calls += 1


class FakeSocketFactory:
    setblocking = FakeStream.setblocking
    setsockopt = FakeStream.setsockopt
    bind = FakeStream.bind
    listen = FakeStream.listen
    accept = FakeStream.accept
    getsockname = FakeStream.getsockname
    getpeername = FakeStream.getpeername
    send = FakeStream.send
    recv = FakeStream.recv
    close = FakeStream.close

    def __init__(self, module):
        self.module = module

    def __call__(self, family, socktype, proto):
        self.module.socket_calls.append((family, socktype, proto))
        return self.module.stream


class TwoArgumentSocketModule:
    """MicroPython-style module exposing only a narrow resolver signature."""

    SOCK_STREAM = 1

    def __init__(self, stream):
        self.stream = stream
        self.resolve_calls = []
        self.socket_calls = []
        self.socket = FakeSocketFactory(self)

    def getaddrinfo(self, *args):
        self.resolve_calls.append(args)
        if len(args) != 2:
            raise TypeError("this port accepts only host and port")
        host, port = args
        return [(2, self.SOCK_STREAM, 6, "", (host, port))]


class MissingServerSocketModule:
    SOCK_STREAM = 1


class IncompleteStream:
    def __init__(self):
        self.close_calls = 0

    def close(self):
        self.close_calls += 1


class RecordingServerKernel:
    def __init__(self, fail_at=None, close_fails=False, supported=True):
        self.fail_at = fail_at
        self.close_fails = close_fails
        self.supported = supported
        self.calls = []
        self.record = object()
        self.listener = object()

    def _call(self, name):
        self.calls.append(name)
        if self.fail_at == name:
            raise RuntimeError("{} failed".format(name))

    def supports_tcp_server(self):
        self.calls.append("supports_tcp_server")
        return self.supported

    def supports_reuse_address(self):
        self.calls.append("supports_reuse_address")
        return True

    def resolve_passive_address(self, host, port):
        self._call("resolve_passive_address")
        self.resolved = (host, port)
        return self.record

    def socket_open(self, record):
        self._call("socket_open")
        self.open_record = record
        return self.listener

    def socket_set_reuse_address(self, listener, enabled):
        self._call("socket_set_reuse_address")
        self.reuse_args = (listener, enabled)

    def socket_bind(self, listener, record):
        self._call("socket_bind")
        self.bind_args = (listener, record)

    def socket_listen(self, listener, backlog):
        self._call("socket_listen")
        self.listen_args = (listener, backlog)

    def socket_setblocking(self, listener, flag):
        self._call("socket_setblocking")
        self.blocking_args = (listener, flag)

    def socket_accept(self, listener):
        self._call("socket_accept")
        return object(), ("192.0.2.1", 5000)

    def socket_retry_mode(self, exc, operation):
        return None

    def socket_close(self, listener):
        self.calls.append("socket_close")
        self.closed_listener = listener
        if self.close_fails:
            raise RuntimeError("close failed")


class DispatchTask:
    priority = 2

    def __init__(self, kernel, spawn_fails=False):
        self.OS = type("OS", (), {"kernel": kernel})()
        self.spawn_fails = spawn_fails
        self.spawn_calls = []

    def spawn(self, routine, **kwargs):
        self.spawn_calls.append((routine, kwargs))
        if self.spawn_fails:
            raise RuntimeError("spawn failed")


class ServerTask(DispatchTask):
    def __init__(self, kernel, output_fails=False):
        super().__init__(kernel)
        self.output_fails = output_fails
        self.OS.print = self._print

    def _print(self, _message):
        if self.output_fails:
            raise RuntimeError("output failed")

    def getID(self):
        return 1


class TestServerKernelContract(unittest.TestCase):
    def test_base_kernel_reports_unsupported_passive_operations(self):
        kernel = Kernel()

        self.assertFalse(kernel.supports_tcp_server())
        self.assertFalse(kernel.supports_reuse_address())
        unsupported_calls = (
            lambda: kernel.resolve_passive_address("", 0),
            lambda: kernel.socket_open(object()),
            lambda: kernel.socket_setblocking(object(), False),
            lambda: kernel.socket_set_reuse_address(object(), True),
            lambda: kernel.socket_bind(object(), object()),
            lambda: kernel.socket_listen(object(), 1),
            lambda: kernel.socket_accept(object()),
            lambda: kernel.socket_local_address(object()),
            lambda: kernel.socket_peer_address(object()),
            lambda: kernel.socket_close(object()),
        )
        for call in unsupported_calls:
            with self.subTest(call=call), self.assertRaises(NotImplementedError):
                call()

    def test_unix_loopback_echo_uses_only_kernel_operations(self):
        kernel = Unix()
        record = kernel.resolve_passive_address("127.0.0.1", 0)
        listener = kernel.socket_open(record)
        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        accepted = None
        try:
            self.assertTrue(kernel.supports_tcp_server())
            self.assertNotIsInstance(record, tuple)
            if kernel.supports_reuse_address():
                kernel.socket_set_reuse_address(listener, True)
            try:
                kernel.socket_bind(listener, record)
            except PermissionError as exc:
                self.skipTest("loopback bind is not permitted: {}".format(exc))
            kernel.socket_listen(listener, 2)
            local_address = kernel.socket_local_address(listener)
            self.assertGreater(local_address[1], 0)

            client.connect(local_address)
            accepted, accepted_address = kernel.socket_accept(listener)
            self.assertEqual(client.getsockname(), accepted_address)
            self.assertEqual(accepted_address, kernel.socket_peer_address(accepted))
            self.assertEqual(local_address, kernel.socket_local_address(accepted))

            client.sendall(b"request")
            self.assertEqual(b"request", kernel.socket_recv(accepted, 7))
            self.assertEqual(8, kernel.socket_send(accepted, b"response"))
            self.assertEqual(b"response", client.recv(8))
        finally:
            if accepted is not None:
                kernel.socket_close(accepted)
            kernel.socket_close(listener)
            client.close()

    def test_unix_nonblocking_accept_exhaustion_is_readable_retry(self):
        kernel = Unix()
        record = kernel.resolve_passive_address("127.0.0.1", 0)
        listener = kernel.socket_open(record)
        try:
            try:
                kernel.socket_bind(listener, record)
            except PermissionError as exc:
                self.skipTest("loopback bind is not permitted: {}".format(exc))
            kernel.socket_listen(listener, 1)
            kernel.socket_setblocking(listener, False)
            with self.assertRaises(BlockingIOError) as raised:
                kernel.socket_accept(listener)
            self.assertEqual(
                "read", kernel.socket_retry_mode(raised.exception, "accept")
            )
        finally:
            kernel.socket_close(listener)

    def test_unix_rejects_passive_record_from_another_kernel(self):
        first = Unix()
        second = Unix()
        record = first.resolve_passive_address("127.0.0.1", 0)

        with self.assertRaises(ValueError):
            second.socket_open(record)
        with self.assertRaises(ValueError):
            second.socket_bind(object(), record)

    def test_peer_address_suppresses_only_not_connected(self):
        unix = Unix()
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self.assertIsNone(unix.socket_peer_address(listener))
        finally:
            listener.close()
        with self.assertRaises(OSError):
            unix.socket_peer_address(listener)

        class FakeErrno:
            ENOTCONN = 57

        stream = FakeStream()
        socket_module = TwoArgumentSocketModule(stream)
        kernel = MicroPythonKernel(
            modules={"socket": socket_module, "errno": FakeErrno()}
        )
        stream.peer_error = OSError(57, "not connected")
        self.assertIsNone(kernel.socket_peer_address(stream))
        stream.peer_error = OSError(9, "bad descriptor")
        with self.assertRaises(OSError):
            kernel.socket_peer_address(stream)

    def test_micropython_complete_port_uses_opaque_record_and_constants(self):
        stream = FakeStream()
        socket_module = TwoArgumentSocketModule(stream)
        socket_module.SOL_SOCKET = 7
        socket_module.SO_REUSEADDR = 9
        kernel = MicroPythonKernel(modules={"socket": socket_module})

        self.assertTrue(kernel.supports_tcp_server())
        self.assertTrue(kernel.supports_reuse_address())
        record = kernel.resolve_passive_address("", 8080)
        self.assertNotIsInstance(record, tuple)
        self.assertEqual(2, len(socket_module.resolve_calls))
        self.assertEqual(("0.0.0.0", 8080), socket_module.resolve_calls[-1])
        self.assertIs(stream, kernel.socket_open(record))

        kernel.socket_set_reuse_address(stream, True)
        kernel.socket_bind(stream, record)
        kernel.socket_listen(stream, 7)
        self.assertEqual([(7, 9, 1)], stream.option_calls)
        self.assertEqual([("0.0.0.0", 8080)], stream.bind_calls)
        self.assertEqual([7], stream.listen_calls)
        self.assertEqual(stream.accept_result, kernel.socket_accept(stream))
        self.assertEqual(stream.local_address, kernel.socket_local_address(stream))
        self.assertEqual(stream.peer_address, kernel.socket_peer_address(stream))

    def test_micropython_does_not_guess_missing_reuse_constants(self):
        kernel = MicroPythonKernel(
            modules={"socket": TwoArgumentSocketModule(FakeStream())}
        )

        self.assertTrue(kernel.supports_tcp_server())
        self.assertFalse(kernel.supports_reuse_address())
        with self.assertRaises(NotImplementedError):
            kernel.socket_set_reuse_address(FakeStream(), True)

    def test_micropython_incomplete_port_reports_unsupported(self):
        kernel = MicroPythonKernel(modules={"socket": MissingServerSocketModule()})

        self.assertFalse(kernel.supports_tcp_server())
        with self.assertRaises(NotImplementedError):
            kernel.resolve_passive_address("", 80)

    def test_micropython_incomplete_opened_stream_closes_once(self):
        stream = IncompleteStream()
        socket_module = TwoArgumentSocketModule(stream)
        kernel = MicroPythonKernel(modules={"socket": socket_module})

        with self.assertRaises(NotImplementedError):
            kernel.socket_open(kernel.resolve_passive_address("", 80))
        self.assertEqual(1, stream.close_calls)

    def test_listener_uses_same_record_for_open_and_bind(self):
        kernel = RecordingServerKernel()

        listener = _open_listener(kernel, "127.0.0.1", 0, 5)

        self.assertIs(kernel.listener, listener)
        self.assertIs(kernel.record, kernel.open_record)
        self.assertIs(kernel.record, kernel.bind_args[1])
        self.assertEqual((kernel.listener, False), kernel.blocking_args)

    def test_listener_capability_failure_precedes_resolution_and_binding(self):
        kernel = RecordingServerKernel(supported=False)

        with self.assertRaises(NotImplementedError):
            _open_listener(kernel, "", 80, 1)

        self.assertEqual(["supports_tcp_server"], kernel.calls)

    def test_listener_post_open_failures_close_once_and_preserve_primary_error(self):
        setup_steps = (
            "socket_set_reuse_address",
            "socket_bind",
            "socket_listen",
            "socket_setblocking",
        )
        for step in setup_steps:
            with self.subTest(step=step):
                kernel = RecordingServerKernel(fail_at=step, close_fails=True)
                with self.assertRaisesRegex(RuntimeError, "{} failed".format(step)):
                    _open_listener(kernel, "", 80, 1)
                self.assertEqual(1, kernel.calls.count("socket_close"))
                self.assertIs(kernel.listener, kernel.closed_listener)

    def test_accepted_stream_failures_close_once_and_preserve_primary_error(self):
        for fail_at, spawn_fails, message in (
            ("socket_setblocking", False, "socket_setblocking failed"),
            (None, True, "spawn failed"),
        ):
            with self.subTest(message=message):
                kernel = RecordingServerKernel(
                    fail_at=fail_at,
                    close_fails=True,
                )
                task = DispatchTask(kernel, spawn_fails=spawn_fails)
                stream = object()
                with self.assertRaisesRegex(RuntimeError, message):
                    _dispatch_client(task, stream, ("192.0.2.1", 5000), {})
                self.assertEqual(1, kernel.calls.count("socket_close"))
                self.assertIs(stream, kernel.closed_listener)

    def test_server_startup_failure_closes_listener_once(self):
        kernel = RecordingServerKernel(close_fails=True)
        task = ServerTask(kernel, output_fails=True)

        with self.assertRaisesRegex(RuntimeError, "output failed"):
            asyncio.run(web_server_task(task, {}))

        self.assertEqual(1, kernel.calls.count("socket_close"))

    def test_server_loop_error_is_not_masked_by_close_failure(self):
        kernel = RecordingServerKernel(fail_at="socket_accept", close_fails=True)
        task = ServerTask(kernel)

        with self.assertRaisesRegex(RuntimeError, "socket_accept failed"):
            asyncio.run(web_server_task(task, {}))

        self.assertEqual(1, kernel.calls.count("socket_close"))


if __name__ == "__main__":
    unittest.main()
