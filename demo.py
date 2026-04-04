"""
Minimal examples for the native smallOS async runtime.

These demos are intentionally focused rather than feature-complete. Each one
exists to show one part of the new mental model:
- ``priority_worker`` shows cooperative sleeping inside an ``async`` task
- ``join_demo`` shows spawning children and waiting for all of them
- ``web_request_demo`` shows a single-threaded non-blocking web request
- ``signal_demo`` shows signal delivery waking a suspended coroutine
- ``cooperative_demo`` shows explicit yielding without sleeping
"""

import errno
import socket

from SmallPackage.SmallOS import SmallOS
from SmallPackage.SmallTask import SmallTask
from SmallPackage.Kernel import Unix


NETWORK_SIGNAL = 3
WEB_REQUEST_HOST = "example.com"
WEB_REQUEST_PORT = 80
WEB_REQUEST_PATH = "/"


async def priority_worker(task):
    """Simple child workload used to show priority-aware interleaving."""
    for step in range(3):
        task.OS.print("[{}] step {}\n".format(task.name, step))
        await task.sleep(0.05)
    return task.name


async def join_demo(task):
    """Spawn three workers and collect their results in a fixed order."""
    task.OS.print("join demo starting\n")

    fast = task.spawn(priority_worker, priority=1, name="fast")
    medium = task.spawn(priority_worker, priority=3, name="medium")
    slow = task.spawn(priority_worker, priority=5, name="slow")

    results = await task.join_all([fast, medium, slow])
    task.OS.print("join demo results: {}\n".format(results))
    return results


async def web_request_task(
    task,
    host=WEB_REQUEST_HOST,
    port=WEB_REQUEST_PORT,
    path=WEB_REQUEST_PATH,
):
    """
    Single-threaded non-blocking HTTP request demo.

    The request socket is put into non-blocking mode and the task explicitly
    awaits readability and writability through the smallOS scheduler. That keeps
    the concurrency model cooperative and single-threaded instead of outsourcing
    progress to worker threads.
    """
    info = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)[0]
    family, socktype, proto, _, sockaddr = info
    sock = socket.socket(family, socktype, proto)
    sock.setblocking(False)

    connect_in_progress = {
        0,
        getattr(errno, "EINPROGRESS", 0),
        getattr(errno, "EWOULDBLOCK", 0),
        getattr(errno, "EALREADY", 0),
        getattr(errno, "EINTR", 0),
        getattr(errno, "EISCONN", 0),
    }

    try:
        err = sock.connect_ex(sockaddr)
        if err not in connect_in_progress:
            raise OSError(err, "connect_ex failed")

        if err != 0:
            await task.wait_writable(sock)
            pending_error = sock.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR)
            if pending_error != 0:
                raise OSError(pending_error, "socket connect failed")

        request = (
            "GET {} HTTP/1.1\r\n"
            "Host: {}\r\n"
            "Connection: close\r\n"
            "User-Agent: smallOS/0.1\r\n"
            "\r\n"
        ).format(path, host).encode("ascii")

        view = memoryview(request)
        while view:
            try:
                sent = sock.send(view)
                if sent == 0:
                    raise RuntimeError("socket closed while sending request")
                view = view[sent:]
            except BlockingIOError:
                await task.wait_writable(sock)

        chunks = []
        while True:
            try:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                chunks.append(chunk)
            except BlockingIOError:
                await task.wait_readable(sock)

        raw_response = b"".join(chunks)
    finally:
        sock.close()

    header_blob, _, body = raw_response.partition(b"\r\n\r\n")
    header_lines = header_blob.splitlines()
    status_line = header_lines[0].decode("utf-8", errors="replace") if header_lines else ""

    return {
        "host": host,
        "port": port,
        "path": path,
        "status_line": status_line,
        "body": body.decode("utf-8", errors="replace"),
    }


async def web_request_demo(task):
    """
    Show a task waiting on a web request while other work keeps running.

    This demo is intentionally not enabled by default because some environments
    do not permit outbound network access. When enabled, the parent task spawns
    the request task, does a bit of unrelated work, and then joins the result.
    """
    task.OS.print("web request demo starting\n")

    request = task.spawn(
        web_request_task,
        priority=max(1, task.priority - 1),
        name="web_request_task",
        args=(WEB_REQUEST_HOST, WEB_REQUEST_PORT, WEB_REQUEST_PATH),
    )

    for step in range(3):
        task.OS.print("web request parent doing other work {}\n".format(step))
        await task.sleep(0.05)

    response = await task.join(request)
    preview = response["body"].replace("\n", " ")
    task.OS.print("web request status: {}\n".format(response["status_line"]))
    task.OS.print("web request preview: {}\n".format(preview[:120]))
    return response


async def signal_sender(task):
    """Sleep for a while and then wake the parent by sending a signal."""
    await task.sleep(0.1)
    task.OS.print("sender raising signal {}\n".format(NETWORK_SIGNAL))
    task.sendSignal(task.parent.pid, NETWORK_SIGNAL)
    return "signal sent"


async def signal_demo(task):
    """Show a task blocking on a signal and then joining the sender."""
    task.OS.print("signal demo waiting\n")
    sender = task.spawn(signal_sender, priority=max(1, task.priority - 1), name="signal_sender")
    signal = await task.wait_signal(NETWORK_SIGNAL)
    sender_result = await task.join(sender)
    task.OS.print("signal demo resumed on {} with {}\n".format(signal, sender_result))
    return sender_result


async def cooperative_demo(task):
    """Show a task voluntarily yielding without waiting on time or signals."""
    for index in range(5):
        task.OS.print("cooperative tick {}\n".format(index))
        await task.yield_now()
    return "done"


if __name__ == "__main__":
    tasks = [
        # SmallTask(2, web_request_demo, name="web_request_demo"),
        # SmallTask(2, join_demo, name="join_demo"),
        SmallTask(4, signal_demo, name="signal_demo"),
        # SmallTask(6, cooperative_demo, name="cooperative_demo"),
    ]

    os = SmallOS().setKernel(Unix())
    os.fork(tasks)
    os.startOS()
