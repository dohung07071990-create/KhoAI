"""SQLite connection creation and transaction lifecycle."""
from __future__ import annotations
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


def connect_db(db_path: Path) -> sqlite3.Connection:
    """Open a configured SQLite connection."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    connection.execute("PRAGMA busy_timeout = 10000")
    return connection


@contextmanager
def db_session(db_path: Path) -> Iterator[sqlite3.Connection]:
    """Commit on success, rollback on error, and always close the connection."""
    connection = connect_db(db_path)
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
