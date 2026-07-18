# pyright: strict

"""Static consumer contract for execution-adapter result inference."""

from SmallPackage.adapters.asyncio_loop import AsyncioAdapter
from SmallPackage.adapters.threads import ThreadAdapter
from SmallPackage._types import ExecutionAdapterLike


def sync_value() -> int:
    return 42


async def async_value() -> int:
    return 42


def accepts_scheduler_adapter(adapter: ExecutionAdapterLike) -> None:
    """Require concrete adapters to satisfy the scheduler's protocol."""


async def verify_adapter_result_types() -> None:
    with ThreadAdapter() as threads:
        accepts_scheduler_adapter(threads)
        thread_result: int = await threads.call(sync_value)

    with AsyncioAdapter() as asyncio_adapter:
        accepts_scheduler_adapter(asyncio_adapter)
        asyncio_result: int = await asyncio_adapter.call(async_value)
        shutdown_error: BaseException | None = asyncio_adapter.shutdown_error

    assert thread_result == asyncio_result
    assert shutdown_error is None
