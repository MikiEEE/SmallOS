#!/usr/bin/env python3
"""Manual snapshot-versus-persistent Unix readiness benchmark.

Performance assertions deliberately stay out of CI. Run this script on each
supported Unix/Python combination and retain the Python version, selector name,
descriptor count, readiness pattern, and medians with review notes.
"""

import argparse
import os
import socket
import statistics
import sys
import time


REPOSITORY_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPOSITORY_ROOT not in sys.path:
    sys.path.insert(0, REPOSITORY_ROOT)

from SmallPackage.Kernel import Unix
from SmallPackage.SmallOS import SmallOS
from SmallPackage.SmallTask import SmallTask


class SnapshotUnix(Unix):
    """Unix kernel forced through the compatibility snapshot path."""

    def create_io_wait_set(self):
        return None


def _elapsed_microseconds(callable_obj, iterations):
    started = time.perf_counter()
    for _ in range(iterations):
        callable_obj()
    return (time.perf_counter() - started) * 1000000 / iterations


def _median_microseconds(callable_obj, iterations, repeats):
    samples = [
        _elapsed_microseconds(callable_obj, iterations)
        for _ in range(repeats)
    ]
    return statistics.median(samples)


def _prime_readiness(socket_pairs, readiness):
    if readiness == "idle":
        return
    selected = socket_pairs[:1] if readiness == "one-ready" else socket_pairs
    for _reader, writer in selected:
        writer.send(b"x")


def benchmark_case(descriptor_count, readiness, iterations, repeats):
    socket_pairs = [socket.socketpair() for _ in range(descriptor_count)]
    readers = [pair[0] for pair in socket_pairs]
    kernel = Unix()
    wait_set = kernel.create_io_wait_set()
    try:
        for reader in readers:
            reader.setblocking(False)
            wait_set.set_interest(reader, True, False)
        _prime_readiness(socket_pairs, readiness)

        snapshot = _median_microseconds(
            lambda: kernel.io_wait(readers, [], 0),
            iterations,
            repeats,
        )
        persistent = _median_microseconds(
            lambda: wait_set.wait(0),
            iterations,
            repeats,
        )
        return snapshot, persistent
    finally:
        wait_set.close()
        for reader, writer in socket_pairs:
            reader.close()
            writer.close()


async def _idle_io_watcher(task, reader):
    await task.wait_readable(reader)


async def _runnable_task(task, iterations):
    for _ in range(iterations):
        await task.yield_now()


def _scheduler_run(kernel_class, iterations):
    reader, writer = socket.socketpair()
    runtime = SmallOS().setKernel(kernel_class())
    watcher = SmallTask(
        1,
        _idle_io_watcher,
        name="idle-io-watcher",
        args=(reader,),
        isWatcher=True,
    )
    runnable = SmallTask(
        2,
        _runnable_task,
        name="runnable-task",
        args=(iterations,),
    )
    runtime.fork([watcher, runnable])
    started = time.perf_counter()
    try:
        runtime.startOS()
        return (time.perf_counter() - started) * 1000000 / iterations
    finally:
        reader.close()
        writer.close()


def benchmark_scheduler(iterations, repeats):
    snapshot_samples = [
        _scheduler_run(SnapshotUnix, iterations)
        for _ in range(repeats)
    ]
    persistent_samples = [
        _scheduler_run(Unix, iterations)
        for _ in range(repeats)
    ]
    return statistics.median(snapshot_samples), statistics.median(persistent_samples)


def _parse_counts(value):
    return [int(item.strip()) for item in value.split(",") if item.strip()]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--counts", default="1,4,32,256")
    parser.add_argument("--iterations", type=int, default=2000)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--scheduler-iterations", type=int, default=10000)
    args = parser.parse_args()

    probe = Unix().create_io_wait_set()
    selector_name = type(probe._selector).__name__
    probe.close()
    print("Python {} | {}".format(sys.version.split()[0], selector_name))
    print("fds  readiness   snapshot_us  persistent_us  speedup")

    for descriptor_count in _parse_counts(args.counts):
        for readiness in ("idle", "one-ready", "all-ready"):
            try:
                snapshot, persistent = benchmark_case(
                    descriptor_count,
                    readiness,
                    args.iterations,
                    args.repeats,
                )
            except OSError as exc:
                print(
                    "{:4d} {:11s} skipped: {}".format(
                        descriptor_count,
                        readiness,
                        exc,
                    )
                )
                break
            speedup = snapshot / persistent if persistent else float("inf")
            print(
                "{:4d} {:11s} {:11.2f} {:14.2f} {:7.2f}x".format(
                    descriptor_count,
                    readiness,
                    snapshot,
                    persistent,
                    speedup,
                )
            )

    snapshot, persistent = benchmark_scheduler(
        args.scheduler_iterations,
        args.repeats,
    )
    speedup = snapshot / persistent if persistent else float("inf")
    print()
    print("Runnable task + one idle I/O watcher (microseconds/scheduler step)")
    print(
        "snapshot {:.2f} | persistent {:.2f} | {:.2f}x".format(
            snapshot,
            persistent,
            speedup,
        )
    )


if __name__ == "__main__":
    main()
