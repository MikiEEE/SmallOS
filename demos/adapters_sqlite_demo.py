"""Use a thread adapter with a user-owned, thread-affine SQLite connection."""

from __future__ import annotations

from collections.abc import Sequence
import sqlite3
import threading

from common import build_runtime, task_runtime

from SmallPackage import SmallTask, Unix
from SmallPackage.adapters.threads import ThreadAdapter


class SQLiteStore:
    """Own a SQLite connection without making it part of SmallOS."""

    def __init__(self) -> None:
        self.connection: sqlite3.Connection | None = None
        self.owner_thread_id: int | None = None

    def open(self) -> None:
        self.owner_thread_id = threading.get_ident()
        self.connection = sqlite3.connect(":memory:")
        self.connection.execute(
            "CREATE TABLE messages (id INTEGER PRIMARY KEY, body TEXT NOT NULL)"
        )

    def _owned_connection(self) -> sqlite3.Connection:
        if self.connection is None:
            raise RuntimeError("SQLite connection is not open")
        if threading.get_ident() != self.owner_thread_id:
            raise RuntimeError("SQLite connection used from the wrong thread")
        return self.connection

    def insert_messages(self, messages: Sequence[str]) -> None:
        connection = self._owned_connection()
        connection.executemany(
            "INSERT INTO messages (body) VALUES (?)",
            [(message,) for message in messages],
        )
        connection.commit()

    def read_messages(self) -> list[tuple[int, str]]:
        cursor = self._owned_connection().execute(
            "SELECT id, body FROM messages ORDER BY id"
        )
        return [(int(row[0]), str(row[1])) for row in cursor.fetchall()]

    def close(self) -> None:
        connection = self._owned_connection()
        connection.close()
        self.connection = None
        self.owner_thread_id = None


async def sqlite_example(
    task: SmallTask[list[tuple[int, str]]],
    adapter: ThreadAdapter,
    store: SQLiteStore,
) -> list[tuple[int, str]]:
    """Create, use, and close SQLite entirely on the adapter worker."""
    await adapter.call(store.open)
    try:
        await adapter.call(
            store.insert_messages,
            ["blocking libraries", "remain cooperative"],
        )
        rows = await adapter.call(store.read_messages)
        task_runtime(task).print("SQLite rows: {}\n".format(rows))
        return rows
    finally:
        await adapter.call(store.close)


def main() -> None:
    runtime = build_runtime(Unix())
    store = SQLiteStore()

    # One worker creates a serialized execution lane for this connection.
    with ThreadAdapter(max_workers=1, max_pending=8) as blocking:
        target = SmallTask(
            2,
            sqlite_example,
            name="sqlite_adapter_example",
            args=(blocking, store),
        )
        runtime.fork(target)
        runtime.start()

    if target.exception is not None:
        raise target.exception


if __name__ == "__main__":
    main()
