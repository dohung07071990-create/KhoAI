"""Retention policy for persisted audit, access and closed-incident records."""
from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Any, Callable


class AuditRetentionService:
    def __init__(self, db_session: Callable[[], Any], business_tz: Any) -> None:
        self.db_session = db_session
        self.business_tz = business_tz

    def prune_old_logs(self, retention_days: int | None = None) -> dict[str, int]:
        """Delete expired audit records while preserving Telegram outbox work."""
        days = retention_days if retention_days is not None else int(os.getenv("KHOAI_LOG_RETENTION_DAYS", "365"))
        access_deleted = events_deleted = system_deleted = 0
        expired_incidents: list[str] = []
        if days > 0:
            cutoff = (datetime.now(self.business_tz) - timedelta(days=days)).isoformat(timespec="seconds")
            with self.db_session() as db:
                has_outbox = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='telegram_outbox'").fetchone()
                if has_outbox:
                    old_ids = [row[0] for row in db.execute("""SELECT id FROM security_events
                        WHERE event_at < ? AND id NOT IN (SELECT event_id FROM telegram_outbox
                        WHERE text_status='pending' OR (text_status='sent' AND photo_status='pending'))""", (cutoff,)).fetchall()]
                else:
                    old_ids = [row[0] for row in db.execute("SELECT id FROM security_events WHERE event_at < ?", (cutoff,)).fetchall()]
                if old_ids:
                    db.executemany("DELETE FROM acknowledged_events WHERE event_id=?", [(event_id,) for event_id in old_ids])
                    if has_outbox:
                        db.executemany("DELETE FROM telegram_outbox WHERE event_id=?", [(event_id,) for event_id in old_ids])
                access_deleted = db.execute("DELETE FROM access_logs WHERE event_at < ?", (cutoff,)).rowcount
                if has_outbox:
                    events_deleted = db.execute("DELETE FROM security_events WHERE event_at < ? AND id NOT IN (SELECT event_id FROM telegram_outbox WHERE text_status='pending' OR (text_status='sent' AND photo_status='pending'))", (cutoff,)).rowcount
                else:
                    events_deleted = db.execute("DELETE FROM security_events WHERE event_at < ?", (cutoff,)).rowcount
                system_deleted = db.execute("DELETE FROM system_access_logs WHERE event_at < ?", (cutoff,)).rowcount
                expired_incidents = [row[0] for row in db.execute(
                    "SELECT incident_id FROM incidents WHERE status='CLOSED' AND closed_at IS NOT NULL AND closed_at < ?", (cutoff,)
                ).fetchall()]
                if expired_incidents:
                    db.executemany("DELETE FROM incident_events WHERE incident_id=?", [(item,) for item in expired_incidents])
                    db.executemany("DELETE FROM incidents WHERE incident_id=?", [(item,) for item in expired_incidents])
        return {"access_logs_deleted": access_deleted, "security_events_deleted": events_deleted,
                "system_access_logs_deleted": system_deleted, "closed_incidents_deleted": len(expired_incidents)}
