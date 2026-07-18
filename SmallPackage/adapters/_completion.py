"""Thread-safe completion queue with a readiness notification socket."""

from __future__ import annotations

import queue
import socket
import threading

from .base import AdapterCompletion
from .errors import AdapterUnavailableError


class CompletionChannel:
    """Move completions between threads without touching scheduler state."""

    def __init__(self) -> None:
        socket_pair = getattr(socket, "socketpair", None)
        if socket_pair is None:
            raise AdapterUnavailableError(
                "this Python runtime does not provide socket.socketpair()"
            )
        try:
            reader, writer = socket_pair()
        except (OSError, TypeError) as exc:
            raise AdapterUnavailableError(
                "could not create the adapter completion socket pair: {}".format(exc)
            ) from exc
        self._reader: socket.socket = reader
        self._writer: socket.socket = writer
        self._reader.setblocking(False)
        self._writer.setblocking(False)
        self._queue: queue.SimpleQueue[AdapterCompletion] = queue.SimpleQueue()
        self._lock: threading.Lock = threading.Lock()
        self._closed: bool = False

    @property
    def wait_object(self) -> socket.socket:
        """Return the socket watched by ``Kernel.io_wait()``."""
        return self._reader

    @property
    def closed(self) -> bool:
        with self._lock:
            return self._closed

    def post(self, completion: AdapterCompletion) -> bool:
        """Enqueue a completion and make the reader socket ready."""
        notification_failed: bool = False
        with self._lock:
            if self._closed:
                return False
            self._queue.put(completion)
            try:
                self._writer.send(b"\x01")
            except BlockingIOError:
                # A full socket is already readable, so no wakeup is lost.
                pass
            except OSError:
                notification_failed = True

        if notification_failed:
            # A completion without a wakeup could strand the scheduler. Mark
            # the channel unusable so the runtime fails affected jobs instead.
            self.close()
            return False
        return True

    def drain(self) -> list[AdapterCompletion]:
        """Drain notification bytes and all completions available now."""
        with self._lock:
            if self._closed:
                return []

        while True:
            try:
                if not self._reader.recv(4096):
                    break
            except BlockingIOError:
                break
            except OSError:
                break

        completions: list[AdapterCompletion] = []
        while True:
            try:
                completions.append(self._queue.get_nowait())
            except queue.Empty:
                break
        return completions

    def close(self) -> None:
        """Close both notification sockets once no further posts are needed."""
        with self._lock:
            if self._closed:
                return
            self._closed = True
            reader = self._reader
            writer = self._writer
        for sock in (reader, writer):
            try:
                sock.close()
            except OSError:
                pass
        while True:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break
