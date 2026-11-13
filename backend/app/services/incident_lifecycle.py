"""Incident lifecycle operations (open/reopen and SAFE+ACK closure)."""
from __future__ import annotations

import json
import secrets
import sqlite3
import time
from datetime import datetime
from typing import Any, Callable


class IncidentLifecycleService:
    def __init__(self, now_business: Callable[[], str], cooldown_seconds: float,
                 siren_seconds: int, detector_state: Callable[[], str]) -> None:
        self.now_business = now_business
        self.cooldown_seconds = max(0.0, float(cooldown_seconds))
        self.siren_seconds = max(1, int(siren_seconds))
        self.detector_state = detector_state

    def open_incident(self, db: sqlite3.Connection, event: dict[str, Any],
                      incident_type: str = "intrusion", *, start_siren: bool = True) -> str:
        now = self.now_business()
        session_id = str(event.get("session_id") or "").strip() or None
        if session_id:
            row = db.execute("SELECT incident_id,status FROM incidents WHERE incident_type=? AND session_id=? ORDER BY started_at DESC LIMIT 1",
                             (incident_type, session_id)).fetchone()
        else:
            row = db.execute("SELECT incident_id FROM incidents WHERE status='OPEN' AND incident_type=? ORDER BY started_at DESC LIMIT 1",
                             (incident_type,)).fetchone()
        siren_until = time.time() + self.siren_seconds if start_siren else 0.0
        if row:
            incident_id = str(row["incident_id"])
            repeated = db.execute("""SELECT event_at FROM incident_events WHERE incident_id=? AND event_type=?
                AND COALESCE(track_id,-1)=COALESCE(?,-1) ORDER BY id DESC LIMIT 1""",
                (incident_id, str(event.get("type") or "alarm"), event.get("track_id"))).fetchone()
            in_cooldown = False
            if repeated:
                try:
                    in_cooldown = abs((datetime.fromisoformat(str(event.get("event_at") or now))
                                       - datetime.fromisoformat(repeated["event_at"])).total_seconds()) < self.cooldown_seconds
                except ValueError:
                    in_cooldown = True
            if start_siren and (not in_cooldown or str(row["status"]).upper() == "CLOSED"):
                db.execute("UPDATE incidents SET status='OPEN',closed_at=NULL,acknowledged=0,acknowledged_at=NULL,siren_until=?,updated_at=? WHERE incident_id=?",
                           (siren_until, now, incident_id))
            else:
                db.execute("UPDATE incidents SET updated_at=? WHERE incident_id=?", (now, incident_id))
            return incident_id
        incident_id = secrets.token_hex(16)
        db.execute("INSERT INTO incidents(incident_id,incident_type,started_at,updated_at,status,acknowledged,siren_until,event_count,summary_json,session_id) VALUES(?,?,?,?,'OPEN',0,?,0,?,?)",
                   (incident_id, incident_type, now, now, siren_until,
                    json.dumps({"first_event": event.get("type"), "track_id": event.get("track_id"), "session_id": session_id}, ensure_ascii=False), session_id))
        return incident_id

    def close_resolved(self, db: sqlite3.Connection) -> None:
        # An intrusion latch closes only after SAFE and administrator acknowledgement.
        if self.detector_state() != "SAFE":
            return
        now = self.now_business()
        db.execute("UPDATE incidents SET status='CLOSED',closed_at=?,updated_at=? WHERE status='OPEN' AND incident_type='intrusion' AND acknowledged=1",
                   (now, now))
