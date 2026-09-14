"""Run blocking and asyncio-owned user code alongside SmallOS tasks."""

from __future__ import annotations

import asyncio
import time

from common import build_runtime, task_runtime

from SmallPackage import SmallTask, Unix
from SmallPackage.adapters.asyncio_loop import AsyncioAdapter
from SmallPackage.adapters.threads import ThreadAdapter


def blocking_library_call(label: str) -> str:
    """Stand in for a user-installed synchronous driver or SDK."""
    time.sleep(0.05)
    return "blocking result for {}".format(label)


async def asyncio_library_call(label: str) -> str:
    """Stand in for a user-installed library that owns asyncio primitives."""
    await asyncio.sleep(0.05)
    return "asyncio result for {}".format(label)


async def blocking_adapter_demo(
    task: SmallTask[str],
    adapter: ThreadAdapter,
) -> str:
    # adapter.call emits a smallOS-owned instruction. The worker thread never
    # mutates scheduler queues or resumes this task directly.
    result = await adapter.call(blocking_library_call, "SmallOS")
    task_runtime(task).print(result + "\n")
    return result


async def asyncio_adapter_demo(
    task: SmallTask[str],
    adapter: AsyncioAdapter,
) -> str:
    # The callable runs on the adapter's persistent asyncio loop, then its result
    # returns through a readiness object watched by the smallOS kernel.
    result = await adapter.call(asyncio_library_call, "SmallOS")
    task_runtime(task).print(result + "\n")
    return result


async def cooperative_peer(task: SmallTask[str]) -> str:
    for index in range(3):
        task_runtime(task).print("SmallOS peer step {}\n".format(index))
        await task.sleep(0.5)
    return "peer complete"


def main() -> None:
    runtime = build_runtime(Unix())
    # Adapter lifetime surrounds runtime.start(): shutdown is explicit, and a
    # live adapter binds to the first SmallOS runtime that submits work to it.
    with ThreadAdapter(max_workers=2, max_pending=8) as blocking:
        with AsyncioAdapter(max_pending=8) as foreign_async:
            runtime.fork(
                [
                    SmallTask(
                        2,
                        blocking_adapter_demo,
                        name="blocking_adapter",
                        args=(blocking,),
                    ),
                    SmallTask(
                        3,
                        asyncio_adapter_demo,
                        name="asyncio_adapter",
                        args=(foreign_async,),
                    ),
                    SmallTask(4, cooperative_peer, name="cooperative_peer"),
                ]
            )
            runtime.start()


if __name__ == "__main__":
    main()
