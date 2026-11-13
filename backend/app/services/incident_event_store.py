"""Persistence operations for incident source events and event linkage."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import Any, Callable


class IncidentEventStore:
    """Persist incident events with cooldown and link source security events."""

    def __init__(self, now_business: Callable[[], str], cooldown_seconds: float) -> None:
        self.now_business = now_business
        self.cooldown_seconds = max(0.0, float(cooldown_seconds))

    def record_event(self, db: sqlite3.Connection, incident_id: str,
                     event: dict[str, Any], source_id: str) -> None:
        event_type = str(event.get("type") or "alarm")
        track_id = event.get("track_id")
        event_at = str(event.get("event_at") or self.now_business())
        last = db.execute("""SELECT event_at FROM incident_events WHERE incident_id=? AND event_type=?
            AND COALESCE(track_id,-1)=COALESCE(?,-1) ORDER BY id DESC LIMIT 1""",
            (incident_id, event_type, track_id)).fetchone()
        if last:
            try:
                delta = abs((datetime.fromisoformat(event_at) - datetime.fromisoformat(last["event_at"])).total_seconds())
            except ValueError:
                delta = 0
            if delta < self.cooldown_seconds:
                return
        try:
            db.execute("INSERT OR IGNORE INTO incident_events(incident_id,source_event_id,event_type,track_id,event_at,details_json) VALUES(?,?,?,?,?,?)",
                       (incident_id, source_id, event_type, track_id, event_at, json.dumps(event, ensure_ascii=False)))
        except sqlite3.IntegrityError:
            return
        db.execute("UPDATE incidents SET event_count=event_count+1,updated_at=? WHERE incident_id=?",
                   (self.now_business(), incident_id))

    @staticmethod
    def link_event(db: sqlite3.Connection, source_id: str, incident_id: str) -> None:
        row = db.execute("SELECT id,details_json FROM security_events WHERE source_event_id=?", (source_id,)).fetchone()
        if not row:
            return
        try:
            details = json.loads(row["details_json"] or "{}")
        except (TypeError, ValueError):
            details = {}
        details["incident_id"] = incident_id
        encoded = json.dumps(details, ensure_ascii=False)
        db.execute("UPDATE security_events SET details_json=? WHERE id=?", (encoded, row["id"]))
        db.execute("UPDATE incident_events SET details_json=? WHERE source_event_id=?", (encoded, source_id))

