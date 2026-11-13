"""Telegram persistence schema and one-time outbox migration."""
from __future__ import annotations
import os
import logging
from datetime import datetime, timedelta
from typing import Any

logger = logging.getLogger("khoai.telegram")

def ensure_telegram_schema(backend: Any, config: Any) -> None:
    replay_hours = max(1, min(168, int(os.getenv("TELEGRAM_REPLAY_HOURS", "6"))))
    with backend.db_session() as db:
        existing_state = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='telegram_delivery_state'").fetchone()
        db.executescript("""
        CREATE TABLE IF NOT EXISTS telegram_delivery_state (
            chat_id INTEGER PRIMARY KEY, last_event_id INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS telegram_outbox (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL, event_id INTEGER NOT NULL,
            severity TEXT NOT NULL, event_at TEXT NOT NULL,
            text_status TEXT NOT NULL DEFAULT 'pending',
            photo_status TEXT NOT NULL DEFAULT 'not_applicable',
            text_attempts INTEGER NOT NULL DEFAULT 0,
            photo_attempts INTEGER NOT NULL DEFAULT 0,
            next_retry_at TEXT,
            last_error TEXT,
            text_message_id INTEGER,
            photo_message_id INTEGER,
            replay_pending INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            UNIQUE(chat_id,event_id)
        );
        CREATE INDEX IF NOT EXISTS idx_telegram_outbox_due
            ON telegram_outbox(chat_id,text_status,photo_status,next_retry_at);
        CREATE TABLE IF NOT EXISTS telegram_instance_lease (
            lease_name TEXT PRIMARY KEY, owner TEXT NOT NULL, expires_at REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS telegram_runtime_state (
            state_key TEXT PRIMARY KEY, state_value TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS telegram_state (
            id INTEGER PRIMARY KEY CHECK(id=1), last_sent_id INTEGER NOT NULL DEFAULT 0
        );
        """)
        outbox_columns = {str(row[1]) for row in db.execute("PRAGMA table_info(telegram_outbox)").fetchall()}
        if "replay_pending" not in outbox_columns:
            db.execute("ALTER TABLE telegram_outbox ADD COLUMN replay_pending INTEGER NOT NULL DEFAULT 0")
        # dev.24.2 cursors mean "processed", not "sent". Replay a bounded
        # window into an idempotent outbox rather than trusting those cursors.
        migration = "2026-11-11_telegram_outbox_v1"
        if not db.execute("SELECT 1 FROM khoai_schema_migrations WHERE migration_id=?", (migration,)).fetchone():
            cutoff = (datetime.now(backend.BUSINESS_TZ) - timedelta(hours=replay_hours)).isoformat(timespec="seconds")
            old_chats = [int(r[0]) for r in db.execute("SELECT chat_id FROM telegram_delivery_state").fetchall()]
            if old_chats:
                rows = db.execute("SELECT id,event_at,severity FROM security_events WHERE severity IN ('warning','severe') AND event_at>=? ORDER BY id", (cutoff,)).fetchall()
                now = backend.now_business()
                for chat_id in old_chats:
                    for row in rows:
                        db.execute("""INSERT OR IGNORE INTO telegram_outbox
                            (chat_id,event_id,severity,event_at,text_status,photo_status,replay_pending,created_at,updated_at)
                            VALUES(?,?,?,?,'pending','pending',?,?,?)""",
                            (chat_id, int(row['id']), row['severity'], row['event_at'],
                             int(row['severity'] == 'warning'), now, now))
            # A 24.1 global cursor is a confirmed-send watermark, so it can
            # safely seed existing chats only when no per-chat cursor existed.
            elif not existing_state:
                state_columns = {str(row[1]) for row in db.execute("PRAGMA table_info(telegram_state)").fetchall()}
                legacy_value = None
                if {"key", "value"}.issubset(state_columns):
                    legacy = db.execute("SELECT value FROM telegram_state WHERE key='last_sent_id' LIMIT 1").fetchone()
                    legacy_value = legacy[0] if legacy else None
                elif "last_sent_id" in state_columns:
                    legacy = db.execute("SELECT last_sent_id FROM telegram_state ORDER BY rowid DESC LIMIT 1").fetchone()
                    legacy_value = legacy[0] if legacy else None
                else:
                    logger.warning("Bỏ qua migration Telegram cursor: schema telegram_state không nhận diện được (cột: %s)", sorted(state_columns))
                try:
                    legacy_cursor = int(legacy_value) if legacy_value is not None else None
                except (TypeError, ValueError):
                    logger.warning("Bỏ qua migration Telegram cursor: last_sent_id cũ không phải số nguyên")
                    legacy_cursor = None
                if legacy_cursor is not None:
                    for chat_id in config.allowed_chat_ids:
                        db.execute("INSERT OR IGNORE INTO telegram_delivery_state(chat_id,last_event_id) VALUES(?,?)", (chat_id, legacy_cursor))
            db.execute("INSERT INTO khoai_schema_migrations(migration_id,applied_at) VALUES(?,?)", (migration, backend.now_business()))
        replay_migration = "2026-11-12_telegram_replay_digest_v2"
        if not db.execute("SELECT 1 FROM khoai_schema_migrations WHERE migration_id=?", (replay_migration,)).fetchone():
            cutoff = (datetime.now(backend.BUSINESS_TZ) - timedelta(hours=replay_hours)).isoformat(timespec="seconds")
            db.execute("""UPDATE telegram_outbox SET replay_pending=1
                WHERE severity='warning' AND text_status='pending' AND event_at>=?""", (cutoff,))
            db.execute("INSERT INTO khoai_schema_migrations(migration_id,applied_at) VALUES(?,?)",
                       (replay_migration, backend.now_business()))
        latest = int(db.execute("SELECT COALESCE(MAX(id),0) FROM security_events").fetchone()[0])
        for chat_id in config.allowed_chat_ids:
            row = db.execute("SELECT 1 FROM telegram_delivery_state WHERE chat_id=?", (chat_id,)).fetchone()
            if not row:
                db.execute("INSERT INTO telegram_delivery_state(chat_id,last_event_id) VALUES(?,?)", (chat_id, latest))
