# pyright: strict, reportUnnecessaryTypeIgnoreComment=true

"""Static contract for operation-aware retries and bytes-like socket sends."""

from typing import Any

from SmallPackage.Kernel import Kernel
from SmallPackage._types import SocketBuffer, SocketKernelLike, SocketOperation


class SocketKernel(Kernel):
    received: SocketBuffer | None = None

    def socket_send(self, sock: Any, data: SocketBuffer) -> int:
        self.received = data
        return len(data)


def accepts_kernel(kernel: SocketKernelLike) -> None:
    """Require the concrete kernel to satisfy the public structural contract."""


def verify_socket_contract() -> None:
    kernel = SocketKernel()
    accepts_kernel(kernel)
    payload = memoryview(b"response")
    sent: int = kernel.socket_send(object(), payload)
    operation: SocketOperation = "send"
    retry_mode = kernel.socket_retry_mode(BlockingIOError(), operation)
    assert sent == len(payload)
    assert kernel.received is payload
    assert retry_mode == "write"

    kernel.socket_retry_mode(BlockingIOError(), "connect")  # pyright: ignore[reportArgumentType]
