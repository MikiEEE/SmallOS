import asyncio
import errno
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "demos"))

from demos.web_app_demo import _read_request_head, _send_all
from SmallPackage.Kernel import Kernel, MicroPythonKernel, Unix
from SmallPackage.clients.SmallStream import SmallStream


class FakeSSLWantReadError(OSError):
    pass


class FakeSSLWantWriteError(OSError):
    pass


class FakeSSLModule:
    SSLWantReadError = FakeSSLWantReadError
    SSLWantWriteError = FakeSSLWantWriteError


class StreamSocket:
    pass


class ConnectWouldBlockSocket:
    def connect(self, _sockaddr):
        raise BlockingIOError()


class StreamKernel(Kernel):
    def __init__(self):
        super().__init__()
        self.send_attempts = []
        self.recv_attempts = 0
        self.handshake_attempts = 0

    def resolve_address(self, host, port):
        return (0, 0, 0, "", (host, port))

    def socket_open(self, address_info):
        return StreamSocket()

    def socket_setblocking(self, sock, flag):
        return None

    def socket_connect(self, sock, sockaddr):
        return True

    def socket_wrap_tls_client(self, sock, **kwargs):
        return sock

    def socket_do_handshake(self, sock):
        self.handshake_attempts += 1
        if self.handshake_attempts == 1:
            raise BlockingIOError(errno.EAGAIN, "try again")

    def socket_send(self, sock, data):
        self.send_attempts.append(data)
        if len(self.send_attempts) == 1:
            raise BlockingIOError(errno.EAGAIN, "try again")
        return len(data)

    def socket_recv(self, sock, buffer_size):
        self.recv_attempts += 1
        if self.recv_attempts == 1:
            raise BlockingIOError(errno.EAGAIN, "try again")
        return b"response"


class DemoStreamKernel(StreamKernel):
    def socket_recv(self, sock, buffer_size):
        self.recv_attempts += 1
        if self.recv_attempts == 1:
            raise BlockingIOError(errno.EAGAIN, "try again")
        return b"GET / HTTP/1.1\r\n\r\n"


class RuntimeRef:
    def __init__(self, kernel):
        self.kernel = kernel


class StreamTask:
    def __init__(self, kernel):
        self.OS = RuntimeRef(kernel)
        self.read_waits = []
        self.write_waits = []

    async def wait_readable(self, sock):
        self.read_waits.append(sock)

    async def wait_writable(self, sock):
        self.write_waits.append(sock)


class TestSocketRetryClassification(unittest.TestCase):
    def test_base_retry_direction_depends_on_operation(self):
        kernel = Kernel()
        error = BlockingIOError(errno.EAGAIN, "try again")

        self.assertEqual("read", kernel.socket_retry_mode(error, "accept"))
        self.assertEqual("read", kernel.socket_retry_mode(error, "recv"))
        self.assertEqual("read", kernel.socket_retry_mode(error, "handshake"))
        self.assertEqual("write", kernel.socket_retry_mode(error, "send"))
        self.assertIsNone(kernel.socket_retry_mode(OSError(errno.EINVAL, "bad"), "recv"))

    def test_unix_retry_mode_preserves_tls_direction(self):
        kernel = Unix()
        pending = BlockingIOError(errno.EAGAIN, "try again")

        self.assertEqual("read", kernel.socket_retry_mode(pending, "recv"))
        self.assertEqual("write", kernel.socket_retry_mode(pending, "send"))
        self.assertEqual(
            "write", kernel.socket_retry_mode(OSError(errno.EAGAIN, "again"), "send")
        )
        self.assertEqual(
            "read",
            kernel.socket_retry_mode(kernel._ssl.SSLWantReadError(), "send"),
        )
        self.assertEqual(
            "write",
            kernel.socket_retry_mode(kernel._ssl.SSLWantWriteError(), "recv"),
        )
        self.assertIsNone(
            kernel.socket_retry_mode(
                BlockingIOError(errno.EINPROGRESS, "pending connect"), "send"
            )
        )

    def test_micropython_matches_unix_and_preserves_tls_direction(self):
        kernel = MicroPythonKernel(modules={"ssl": FakeSSLModule()})
        pending = OSError(errno.EAGAIN, "try again")

        self.assertEqual("read", kernel.socket_retry_mode(pending, "accept"))
        self.assertEqual("read", kernel.socket_retry_mode(pending, "recv"))
        self.assertEqual("write", kernel.socket_retry_mode(pending, "send"))
        self.assertEqual(
            "read", kernel.socket_retry_mode(FakeSSLWantReadError(), "send")
        )
        self.assertEqual(
            "write", kernel.socket_retry_mode(FakeSSLWantWriteError(), "recv")
        )
        self.assertIsNone(
            kernel.socket_retry_mode(OSError(115, "pending connect"), "recv")
        )

    def test_micropython_connect_preserves_errno_less_would_block(self):
        kernel = MicroPythonKernel()

        self.assertFalse(kernel.socket_connect(ConnectWouldBlockSocket(), ("host", 80)))

    def test_unknown_operation_is_rejected_before_classification(self):
        kernels = (Kernel(), Unix(), MicroPythonKernel())

        for kernel in kernels:
            with self.subTest(kernel=type(kernel).__name__):
                with self.assertRaisesRegex(ValueError, "Unknown socket operation"):
                    kernel.socket_retry_mode(BlockingIOError(), "connect")

    def test_small_stream_forwards_memoryview_and_waits_by_operation(self):
        kernel = StreamKernel()
        task = StreamTask(kernel)
        stream = SmallStream(task, "example.test", 80)
        stream.sock = StreamSocket()
        stream._connected = True
        payload = memoryview(b"request")

        async def exercise_stream():
            await stream.send_all(payload)
            return await stream.recv_some()

        result = asyncio.run(exercise_stream())

        self.assertEqual(b"response", result)
        self.assertIs(payload, kernel.send_attempts[0])
        self.assertEqual([stream.sock], task.write_waits)
        self.assertEqual([stream.sock], task.read_waits)

    def test_small_stream_handshake_waits_for_readability(self):
        kernel = StreamKernel()
        task = StreamTask(kernel)
        stream = SmallStream(task, "example.test", 443, use_tls=True)

        result = asyncio.run(stream.connect())

        self.assertIs(stream, result)
        self.assertEqual(2, kernel.handshake_attempts)
        self.assertEqual([stream.sock], task.read_waits)
        self.assertEqual([], task.write_waits)

    def test_web_demo_routes_send_and_recv_backpressure_by_operation(self):
        kernel = DemoStreamKernel()
        task = StreamTask(kernel)
        sock = StreamSocket()

        async def exercise_helpers():
            await _send_all(task, sock, memoryview(b"response"))
            return await _read_request_head(task, sock)

        result = asyncio.run(exercise_helpers())

        self.assertEqual(b"GET / HTTP/1.1\r\n\r\n", result)
        self.assertEqual([sock], task.write_waits)
        self.assertEqual([sock], task.read_waits)


if __name__ == "__main__":
    unittest.main()
