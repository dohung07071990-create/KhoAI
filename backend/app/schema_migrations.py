"""Forward-only SQLite schema migrations and first-admin bootstrap."""
from __future__ import annotations
import os
import sqlite3
from typing import Callable

def migrate_schema(db: sqlite3.Connection, now_business: Callable[[], str], hash_password: Callable[[str], str]) -> None:
    """Apply idempotent migrations while preserving existing data."""
    # Enforce case-insensitive uniqueness for both fresh and pre-existing databases.
    username_duplicates = db.execute("""SELECT lower(username) AS normalized, COUNT(*) AS n
        FROM admin_users GROUP BY lower(username) HAVING COUNT(*) > 1 LIMIT 1""").fetchone()
    if username_duplicates:
        raise RuntimeError("Database có username trùng khác hoa/thường; cần quản trị viên xử lý trùng tên trước khi khởi động.")
    db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_admin_users_username_nocase ON admin_users(username COLLATE NOCASE)")
    # [INTEGRATED] Migrate existing KhoAI databases without deleting existing records.
    event_columns = {row["name"] for row in db.execute("PRAGMA table_info(security_events)").fetchall()}
    if "source_event_id" not in event_columns:
        db.execute("ALTER TABLE security_events ADD COLUMN source_event_id TEXT")
    db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_security_source_event_id ON security_events(source_event_id) WHERE source_event_id IS NOT NULL")
    existing = {row["name"] for row in db.execute("PRAGMA table_info(cards)").fetchall()}
    for column, declaration in (
        ("expires_at", "TEXT"), ("daily_quota", "INTEGER NOT NULL DEFAULT 3"),
        ("used_today", "INTEGER NOT NULL DEFAULT 0"), ("last_reset_date", "TEXT"), ("color", "TEXT")
    ):
        if column not in existing:
            db.execute(f"ALTER TABLE cards ADD COLUMN {column} {declaration}")
    session_columns = {row["name"] for row in db.execute("PRAGMA table_info(admin_sessions)").fetchall()}
    if "operator_name" not in session_columns:
        db.execute("ALTER TABLE admin_sessions ADD COLUMN operator_name TEXT NOT NULL DEFAULT 'Quản trị viên (token dùng chung)'")
    if "user_id" not in session_columns:
        db.execute("ALTER TABLE admin_sessions ADD COLUMN user_id INTEGER")
    if "role" not in session_columns:
        db.execute("ALTER TABLE admin_sessions ADD COLUMN role TEXT NOT NULL DEFAULT 'admin'")
    # One-time security migration: invalidate legacy raw-cookie sessions and erase
    # raw session IDs from historical audit records before hashed IDs are introduced.
    migration_id = "2026-11-11_session_digest_v1"
    if not db.execute("SELECT 1 FROM khoai_schema_migrations WHERE migration_id=?", (migration_id,)).fetchone():
        db.execute("DELETE FROM admin_sessions")
        db.execute("UPDATE system_access_logs SET session_id=NULL")
        db.execute("INSERT INTO khoai_schema_migrations(migration_id,applied_at) VALUES(?,?)", (migration_id, now_business()))
    # Optional first-run bootstrap; credentials are read only from environment, never hard-coded.
    bootstrap_user = os.getenv("KHOAI_BOOTSTRAP_ADMIN_USERNAME", "").strip()
    bootstrap_pass = os.getenv("KHOAI_BOOTSTRAP_ADMIN_PASSWORD", "")
    if bootstrap_user and bootstrap_pass and not db.execute("SELECT 1 FROM admin_users LIMIT 1").fetchone():
        if len(bootstrap_pass) < 12:
            raise RuntimeError("KHOAI_BOOTSTRAP_ADMIN_PASSWORD phải có ít nhất 12 ký tự.")
        db.execute("INSERT INTO admin_users(username,display_name,password_hash,role,created_at) VALUES(?,?,?,?,?)",
                   (bootstrap_user, os.getenv("KHOAI_BOOTSTRAP_ADMIN_NAME", "Quản trị viên"),
                    hash_password(bootstrap_pass), "admin", now_business()))
    incident_columns = {row["name"] for row in db.execute("PRAGMA table_info(incidents)").fetchall()}
    if "incident_type" not in incident_columns:
        db.execute("ALTER TABLE incidents ADD COLUMN incident_type TEXT NOT NULL DEFAULT 'intrusion'")
    if "session_id" not in incident_columns:
        db.execute("ALTER TABLE incidents ADD COLUMN session_id TEXT")
    db.execute("CREATE INDEX IF NOT EXISTS idx_incidents_session ON incidents(session_id, status)")
