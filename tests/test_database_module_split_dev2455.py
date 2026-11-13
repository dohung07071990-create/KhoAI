from pathlib import Path

from backend.app.database import connect_db, db_session, initialize_database
from backend.app.schema_migrations import migrate_schema
from backend.app.schema_tables import create_schema_tables
from backend.app.sqlite_connection import connect_db as low_level_connect_db


def test_database_facade_preserves_connection_exports():
    assert connect_db is low_level_connect_db
    assert callable(db_session)
    assert callable(create_schema_tables)
    assert callable(migrate_schema)


def test_database_initialization_is_repeatable_and_preserves_records(tmp_path: Path):
    db_path = tmp_path / "nested" / "khoai.sqlite3"
    now = lambda: "2026-11-12T00:00:00+07:00"
    hash_password = lambda value: "test-hash:" + value

    initialize_database(db_path, now, hash_password)
    with db_session(db_path) as db:
        db.execute(
            "INSERT INTO inventory(sku,name,registered_quantity,updated_at) VALUES(?,?,?,?)",
            ("SKU-1", "Test item", 4, now()),
        )

    initialize_database(db_path, now, hash_password)
    with db_session(db_path) as db:
        row = db.execute("SELECT name,registered_quantity FROM inventory WHERE sku='SKU-1'").fetchone()
        assert tuple(row) == ("Test item", 4)
        assert db.execute("SELECT 1 FROM khoai_schema_migrations WHERE migration_id='2026-11-11_session_digest_v1'").fetchone()
