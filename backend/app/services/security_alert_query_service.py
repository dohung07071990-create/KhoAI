"""Read-side queries for security alert records."""
from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any


class SecurityAlertQueryService:
    def __init__(self, db_session: Callable[[], Any], mask_uid_payload: Callable[[Any], Any]) -> None:
        self.db_session = db_session
        self.mask_uid_payload = mask_uid_payload

    def list_alerts(self, role: str | None, limit: int, severity: str) -> list[dict[str, Any]]:
        severity_sql = {"alerts": "e.severity IN ('warning','severe')", "info": "e.severity='info'", "warning": "e.severity='warning'", "severe": "e.severity='severe'", "all": "1=1"}[severity]
        with self.db_session() as db:
            rows = db.execute(f"""SELECT e.*, CASE WHEN a.event_id IS NULL THEN 0 ELSE 1 END AS handled
                FROM security_events e LEFT JOIN acknowledged_events a ON a.event_id=e.id
                WHERE {severity_sql} ORDER BY e.id DESC LIMIT ?""", (limit,)).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            try:
                item["details"] = json.loads(item.pop("details_json"))
            except (ValueError, TypeError):
                item["details"] = {}
            details = item.get("details") or {}
            item.setdefault("level", item.get("severity", "warning")); item.setdefault("kind", item.get("event_type", "camera_event"))
            item.setdefault("ts", item.get("event_at")); item.setdefault("zone", details.get("zone")); item.setdefault("uid", details.get("uid"))
            result.append(item)
        return result if role == "admin" else self.mask_uid_payload(result)
