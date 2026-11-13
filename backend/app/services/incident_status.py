"""Read-only aggregation of active incident state."""
from __future__ import annotations

import sqlite3
import time
from typing import Any, Callable


class IncidentStatusService:
    """Build dashboard incident status from persistence and detector state."""

    def __init__(self, db_session: Callable[[], Any], detector_state: Callable[[], str],
                 wall_time: Callable[[], float] | None = None) -> None:
        self.db_session = db_session
        self.detector_state = detector_state
        self.wall_time = wall_time or (lambda: time.time())

    def get_status(self) -> dict[str, Any]:
        try:
            with self.db_session() as db:
                rows = db.execute(
                    "SELECT * FROM incidents WHERE status='OPEN' ORDER BY started_at DESC"
                ).fetchall()
                if not rows:
                    return {"incident_id": None, "latched": False, "acknowledged": False,
                            "siren": False, "incidents": []}
                active_state = self.detector_state()
                incidents = []
                for row in rows:
                    item = dict(row)
                    acknowledged = bool(item["acknowledged"])
                    siren = (float(item["siren_until"]) > 0
                             and self.wall_time() < float(item["siren_until"]))
                    incidents.append({
                        "incident_id": item["incident_id"],
                        "type": item.get("incident_type", "intrusion"),
                        "status": "OPEN", "acknowledged": acknowledged,
                        "started_at": item["started_at"], "updated_at": item["updated_at"],
                        "event_count": item["event_count"], "siren": siren,
                    })
                intrusion_rows = [row for row in rows if row["incident_type"] == "intrusion"]
                latched = bool(intrusion_rows)
                acknowledged_all = all(bool(row["acknowledged"]) for row in rows)
                siren_active = any(item["siren"] for item in incidents)
                latest = rows[0]
                return {
                    "incident_id": latest["incident_id"], "latched": latched,
                    "acknowledged": acknowledged_all, "siren": siren_active,
                    "alarm": "severe" if active_state == "ALARM" or latched else "off",
                    "active_threat": active_state == "ALARM", "incidents": incidents,
                }
        except sqlite3.OperationalError:
            return {"incident_id": None, "latched": False, "acknowledged": False,
                    "siren": False, "incidents": []}

    def augment_detector_status(self, status: dict[str, Any]) -> dict[str, Any]:
        incident = self.get_status()
        status["live_alarm_state"] = status.get("alarm_state", "UNKNOWN")
        status.update({"latched": incident["latched"], "acknowledged": incident["acknowledged"],
                       "siren": incident["siren"], "incidents": incident["incidents"],
                       "incident_id": incident["incident_id"]})
        if incident["latched"]:
            status["alarm"] = "severe"
            status["alarm_state"] = "ALARM"
        return status
