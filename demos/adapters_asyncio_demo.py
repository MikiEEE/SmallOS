"""Reuse standard-library asyncio resources on one persistent adapter loop."""

from __future__ import annotations

import asyncio

from common import build_runtime, task_runtime

from SmallPackage import SmallTask, Unix
from SmallPackage.adapters.asyncio_loop import AsyncioAdapter


class AsyncioWorker:
    """Own a queue and background task that live on the adapter loop."""

    def __init__(self) -> None:
        self.queue: asyncio.Queue[
            tuple[str, asyncio.Future[str]] | None
        ] | None = None
        self.worker_task: asyncio.Task[None] | None = None
        self.owner_loop_id: int | None = None

    def _check_loop(self) -> int:
        loop_id = id(asyncio.get_running_loop())
        if self.owner_loop_id is not None and loop_id != self.owner_loop_id:
            raise RuntimeError("asyncio resource used from the wrong event loop")
        return loop_id

    async def open(self) -> int:
        self.owner_loop_id = self._check_loop()
        self.queue = asyncio.Queue()
        self.worker_task = asyncio.create_task(self._run())
        return self.owner_loop_id

    async def _run(self) -> None:
        self._check_loop()
        queue = self.queue
        if queue is None:
            raise RuntimeError("asyncio worker is not open")
        while True:
            item = await queue.get()
            if item is None:
                return
            message, response = item
            await asyncio.sleep(0)
            response.set_result(message.upper())

    async def process(self, message: str) -> tuple[str, int]:
        loop_id = self._check_loop()
        queue = self.queue
        if queue is None:
            raise RuntimeError("asyncio worker is not open")
        response: asyncio.Future[str] = asyncio.get_running_loop().create_future()
        await queue.put((message, response))
        return await response, loop_id

    async def close(self) -> None:
        self._check_loop()
        if self.queue is not None:
            await self.queue.put(None)
        if self.worker_task is not None:
            await self.worker_task
        self.queue = None
        self.worker_task = None
        self.owner_loop_id = None


async def asyncio_example(
    task: SmallTask[tuple[str, str]],
    adapter: AsyncioAdapter,
    service: AsyncioWorker,
) -> tuple[str, str]:
    """Create and reuse a loop-affine service across adapter calls."""
    opened_loop = await adapter.call(service.open)
    try:
        first, first_loop = await adapter.call(service.process, "smallos")
        second, second_loop = await adapter.call(service.process, "asyncio")
    finally:
        await adapter.call(service.close)

    if opened_loop != first_loop or first_loop != second_loop:
        raise RuntimeError("adapter calls did not reuse one asyncio loop")

    task_runtime(task).print("Asyncio replies: {}, {}\n".format(first, second))
    return first, second


def main() -> None:
    runtime = build_runtime(Unix())
    service = AsyncioWorker()

    with AsyncioAdapter(max_pending=8) as foreign_async:
        target = SmallTask(
            2,
            asyncio_example,
            name="asyncio_adapter_example",
            args=(foreign_async, service),
        )
        runtime.fork(target)
        runtime.start()

    if target.exception is not None:
        raise target.exception


if __name__ == "__main__":
    main()
