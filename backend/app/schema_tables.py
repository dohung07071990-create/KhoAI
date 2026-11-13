"""Create the current KhoAI SQLite schema (tables and indexes only)."""
from __future__ import annotations
import sqlite3

def create_schema_tables(db: sqlite3.Connection) -> None:
    """Create missing tables and indexes without altering existing records."""
    db.executescript("""
    CREATE TABLE IF NOT EXISTS cards (
        uid TEXT PRIMARY KEY, name TEXT NOT NULL,
        age INTEGER NOT NULL CHECK (age BETWEEN 0 AND 120),
        active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)), created_at TEXT NOT NULL,
        expires_at TEXT, daily_quota INTEGER NOT NULL DEFAULT 3, used_today INTEGER NOT NULL DEFAULT 0,
        last_reset_date TEXT, color TEXT
    );
    CREATE TABLE IF NOT EXISTS access_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT, uid TEXT NOT NULL, card_name TEXT,
        event_at TEXT NOT NULL, result TEXT NOT NULL CHECK (result IN ('allow', 'deny'))
    );
    CREATE INDEX IF NOT EXISTS idx_access_logs_event_at ON access_logs(event_at DESC);
    CREATE TABLE IF NOT EXISTS rfid_scan_guard (
        device_id TEXT NOT NULL, uid TEXT NOT NULL, last_allowed_at REAL NOT NULL,
        PRIMARY KEY(device_id,uid)
    );
    CREATE TABLE IF NOT EXISTS inventory (
        sku TEXT PRIMARY KEY, name TEXT NOT NULL,
        registered_quantity INTEGER NOT NULL CHECK (registered_quantity >= 0),
        updated_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS security_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT, event_at TEXT NOT NULL,
        event_type TEXT NOT NULL, track_id INTEGER, severity TEXT NOT NULL,
        message TEXT NOT NULL, details_json TEXT NOT NULL DEFAULT '{}', source_event_id TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_security_events_at ON security_events(event_at DESC);
    CREATE INDEX IF NOT EXISTS idx_access_logs_uid ON access_logs(uid);
    CREATE TABLE IF NOT EXISTS card_permissions (
        uid TEXT NOT NULL, zone TEXT NOT NULL, PRIMARY KEY(uid, zone)
    );
    CREATE TABLE IF NOT EXISTS pickup_orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT, uid TEXT NOT NULL, item TEXT NOT NULL,
        boxes INTEGER NOT NULL DEFAULT 0, zone TEXT, day TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS device_heartbeats (
        device_id TEXT PRIMARY KEY, last_seen TEXT NOT NULL, alarm TEXT NOT NULL DEFAULT 'off'
    );
    CREATE TABLE IF NOT EXISTS acknowledged_events (
        event_id INTEGER PRIMARY KEY, acknowledged_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS admin_users (
        user_id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT COLLATE NOCASE NOT NULL UNIQUE,
        display_name TEXT NOT NULL, password_hash TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'admin' CHECK(role IN ('admin','viewer')),
        active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)), created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS admin_sessions (
        session_id TEXT PRIMARY KEY, created_at REAL NOT NULL, expires_at REAL NOT NULL,
        operator_name TEXT NOT NULL DEFAULT 'Quản trị viên (token dùng chung)',
        user_id INTEGER, role TEXT NOT NULL DEFAULT 'admin'
    );
    CREATE TABLE IF NOT EXISTS system_access_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_at TEXT NOT NULL,
        event_type TEXT NOT NULL,
        operator_name TEXT NOT NULL,
        session_id TEXT,
        ip_address TEXT,
        user_agent TEXT,
        method TEXT,
        path TEXT,
        details TEXT NOT NULL DEFAULT ''
    );
    CREATE INDEX IF NOT EXISTS idx_system_access_logs_at ON system_access_logs(event_at DESC);
    CREATE INDEX IF NOT EXISTS idx_system_access_logs_session ON system_access_logs(session_id);
    CREATE INDEX IF NOT EXISTS idx_admin_sessions_expiry ON admin_sessions(expires_at);
    CREATE TABLE IF NOT EXISTS khoai_schema_migrations (
        migration_id TEXT PRIMARY KEY, applied_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS incidents (
        incident_id TEXT PRIMARY KEY, incident_type TEXT NOT NULL DEFAULT 'intrusion',
        started_at TEXT NOT NULL, updated_at TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'OPEN', acknowledged INTEGER NOT NULL DEFAULT 0,
        acknowledged_at TEXT, siren_until REAL NOT NULL, event_count INTEGER NOT NULL DEFAULT 0,
        summary_json TEXT NOT NULL DEFAULT '{}', closed_at TEXT, session_id TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_incidents_status ON incidents(status, updated_at DESC);
    CREATE TABLE IF NOT EXISTS incident_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT, incident_id TEXT NOT NULL,
        source_event_id TEXT NOT NULL UNIQUE, event_type TEXT NOT NULL,
        track_id INTEGER, event_at TEXT NOT NULL, details_json TEXT NOT NULL DEFAULT '{}',
        FOREIGN KEY(incident_id) REFERENCES incidents(incident_id)
    );
    CREATE INDEX IF NOT EXISTS idx_incident_events_incident ON incident_events(incident_id, id);
    """)
