"""Static consumer contract for passive TCP kernels."""

from SmallPackage.Kernel import Unix
from SmallPackage._types import PassiveTCPKernelLike


kernel: PassiveTCPKernelLike = Unix()
address = kernel.resolve_passive_address("127.0.0.1", 0)
listener = kernel.socket_open(address)
kernel.socket_bind(listener, address)
