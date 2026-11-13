"""Database initialization facade; connection and schema concerns are delegated."""
from __future__ import annotations
from pathlib import Path
from typing import Callable
from .sqlite_connection import connect_db, db_session
from .schema_tables import create_schema_tables
from .schema_migrations import migrate_schema


def initialize_database(db_path: Path, now_business: Callable[[], str], hash_password: Callable[[str], str]) -> None:
    """Create schema and apply forward-only migrations in one transaction."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with db_session(db_path) as db:
        create_schema_tables(db)
        migrate_schema(db, now_business, hash_password)


__all__ = ["connect_db", "db_session", "initialize_database"]
