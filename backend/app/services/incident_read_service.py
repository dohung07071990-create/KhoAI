"""Read-side queries for persisted incident records and their event timelines."""
from __future__ import annotations

import json
import time
from collections.abc import Callable
from typing import Any


class IncidentReadService:
    def __init__(self, db_session: Callable[[], Any], mask_uid_payload: Callable[[Any], Any],
                 wall_time: Callable[[], float] | None = None) -> None:
        self.db_session = db_session
        self.mask_uid_payload = mask_uid_payload
        self.wall_time = wall_time or time.time

    def list_incidents(self, role: str | None, limit: int) -> list[dict[str, Any]]:
        with self.db_session() as db:
            rows = db.execute("SELECT * FROM incidents ORDER BY started_at DESC LIMIT ?", (limit,)).fetchall()
            result = []
            for row in rows:
                item = dict(row)
                item["acknowledged"] = bool(item["acknowledged"])
                item["type"] = item.get("incident_type", "intrusion")
                item["siren"] = item["status"] == "OPEN" and float(item["siren_until"]) > 0 and self.wall_time() < float(item["siren_until"])
                event_rows = db.execute("SELECT event_type,track_id,event_at,details_json FROM incident_events WHERE incident_id=? ORDER BY id DESC LIMIT 100", (item["incident_id"],)).fetchall()
                item["events"] = []
                for event_row in event_rows:
                    try:
                        details = json.loads(event_row["details_json"] or "{}")
                    except (TypeError, ValueError):
                        details = {}
                    item["events"].append({"type": event_row["event_type"], "track_id": event_row["track_id"], "event_at": event_row["event_at"], "details": details})
                result.append(item)
        return result if role == "admin" else self.mask_uid_payload(result)

