"""HTTP endpoints for security-alert queries and acknowledgement."""
from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, Query, Request, HTTPException


def create_security_alerts_router(services: Any) -> APIRouter:
    router = APIRouter()

    @router.get("/api/alerts", dependencies=[Depends(services.require_session)])
    def list_alerts(
        request: Request,
        limit: int = Query(default=100, ge=1, le=500),
        severity: str = Query(default="alerts", pattern="^(alerts|info|all|warning|severe)$"),
    ) -> list[dict[str, Any]]:
        query_service = getattr(services, "incident_query_service", None)
        if query_service is not None:
            return query_service.list_alerts(getattr(request.state, "khoai_role", None), limit, severity)
        severity_sql = {
            "alerts": "e.severity IN ('warning','severe')", "info": "e.severity='info'",
            "warning": "e.severity='warning'", "severe": "e.severity='severe'", "all": "1=1",
        }[severity]
        with services.db_session() as db:
            rows = db.execute(
                "SELECT e.*, CASE WHEN a.event_id IS NULL THEN 0 ELSE 1 END AS handled "
                "FROM security_events e LEFT JOIN acknowledged_events a ON a.event_id=e.id "
                f"WHERE {severity_sql} ORDER BY e.id DESC LIMIT ?", (limit,),
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            try:
                item["details"] = json.loads(item.pop("details_json"))
            except (ValueError, TypeError):
                item["details"] = {}
            details = item.get("details") or {}
            item.setdefault("level", item.get("severity", "warning"))
            item.setdefault("kind", item.get("event_type", "camera_event"))
            item.setdefault("ts", item.get("event_at"))
            item.setdefault("zone", details.get("zone"))
            item.setdefault("uid", details.get("uid"))
            result.append(item)
        return result if getattr(request.state, "khoai_role", None) == "admin" else services.mask_uid_payload(result)

    @router.post("/api/alerts/{event_id}/ack", dependencies=[Depends(services.require_admin)])
    def acknowledge_alert(event_id: int) -> dict[str, Any]:
        command = getattr(services, "acknowledge_alert_command", None)
        if command is not None:
            return command(event_id)
        with services.db_session() as db:
            exists = db.execute("SELECT id FROM security_events WHERE id=?", (event_id,)).fetchone()
            if not exists:
                raise HTTPException(status_code=404, detail="Không tìm thấy cảnh báo.")
            db.execute("INSERT OR IGNORE INTO acknowledged_events(event_id,acknowledged_at) VALUES(?,?)",
                       (event_id, services.now_business()))
        return {"ok": True, "alarm": services.current_alarm_level()}

    return router
