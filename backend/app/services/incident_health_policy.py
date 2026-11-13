"""Health-incident classification and recovery policy.

This module owns health-incident policy only; persistence primitives for
intrusion incidents remain in IncidentStore.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any, Callable


class IncidentHealthPolicy:
    def __init__(self, now_business: Callable[[], str]) -> None:
        self.now_business = now_business

    @staticmethod
    def incident_type(event_type: str | None = None,
                      health_reason: str | None = None) -> str:
        camera_faults = {"camera_offline", "camera_unstable"}
        return "camera_outage" if event_type in camera_faults or health_reason in camera_faults else "ai_health"

    def close_recovered(self, db: sqlite3.Connection, event: dict[str, Any]) -> None:
        incident_type = "camera_outage" if event.get("type") == "camera_recovered" else None
        event_at = str(event.get("event_at") or self.now_business())
        updated_at = self.now_business()
        if incident_type:
            db.execute(
                "UPDATE incidents SET status='CLOSED',closed_at=?,updated_at=? WHERE status='OPEN' AND incident_type=?",
                (event_at, updated_at, incident_type),
            )
        else:
            db.execute(
                "UPDATE incidents SET status='CLOSED',closed_at=?,updated_at=? WHERE status='OPEN' AND incident_type IN ('camera_outage','ai_health')",
                (event_at, updated_at),
            )
