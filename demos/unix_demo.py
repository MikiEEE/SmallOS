"""Desktop demo for running smallOS on the Unix kernel."""

from common import build_runtime, default_tasks

from SmallPackage.Kernel import Unix


def main():
    # Unix supplies desktop timing, terminal output, sockets, and selector-based
    # readiness while the runtime remains responsible for task ordering.
    runtime = build_runtime(Unix())
    # Registration assigns PIDs but does not execute user routines yet.
    runtime.fork(default_tasks("Unix"))
    # startOS() drives the scheduler until no non-watcher work remains.
    runtime.startOS()


if __name__ == "__main__":
    main()
