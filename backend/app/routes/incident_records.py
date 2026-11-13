"""HTTP endpoints for incident records and incident-level commands."""
from __future__ import annotations

import json
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request


def create_incident_records_router(services: Any) -> APIRouter:
    router = APIRouter()

    @router.get("/api/incidents", dependencies=[Depends(services.require_session)])
    def list_incidents(request: Request, limit: int = Query(default=50, ge=1, le=200)) -> list[dict[str, Any]]:
        query_service = getattr(services, "incident_query_service", None)
        if query_service is not None:
            return query_service.list_incidents(getattr(request.state, "khoai_role", None), limit)
        # Compatibility fallback for standalone router consumers.
        with services.db_session() as db:
            rows = db.execute("SELECT * FROM incidents ORDER BY started_at DESC LIMIT ?", (limit,)).fetchall()
            result = []
            for row in rows:
                item = dict(row)
                item["acknowledged"] = bool(item["acknowledged"])
                item["type"] = item.get("incident_type", "intrusion")
                item["siren"] = (item["status"] == "OPEN" and float(item["siren_until"]) > 0
                                 and time.time() < float(item["siren_until"]))
                event_rows = db.execute(
                    "SELECT event_type,track_id,event_at,details_json FROM incident_events "
                    "WHERE incident_id=? ORDER BY id DESC LIMIT 100", (item["incident_id"],)
                ).fetchall()
                item["events"] = []
                for event_row in event_rows:
                    try:
                        details = json.loads(event_row["details_json"] or "{}")
                    except (TypeError, ValueError):
                        details = {}
                    item["events"].append({"type": event_row["event_type"], "track_id": event_row["track_id"],
                                           "event_at": event_row["event_at"], "details": details})
                result.append(item)
        return result if getattr(request.state, "khoai_role", None) == "admin" else services.mask_uid_payload(result)

    @router.post("/api/incidents/{incident_id}/ack", dependencies=[Depends(services.require_admin)])
    def acknowledge_incident(incident_id: str) -> dict[str, Any]:
        with services.db_session() as db:
            row = db.execute("SELECT status FROM incidents WHERE incident_id=?", (incident_id,)).fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Không tìm thấy incident.")
            if row["status"] != "OPEN":
                raise HTTPException(status_code=409, detail="Incident đã đóng.")
            stamp = services.now_business()
            db.execute("UPDATE incidents SET acknowledged=1,acknowledged_at=?,updated_at=? WHERE incident_id=?",
                       (stamp, stamp, incident_id))
            services.close_incident_if_resolved(db)
        return {"ok": True, **services.incident_status()}

    @router.post("/api/incidents/ack-all", dependencies=[Depends(services.require_admin)])
    def acknowledge_all_incidents() -> dict[str, Any]:
        command = getattr(services, "acknowledge_all_incidents", None)
        if command is not None:
            return command()
        stamp = services.now_business()
        with services.db_session() as db:
            cursor = db.execute(
                "UPDATE incidents SET acknowledged=1, acknowledged_at=?, updated_at=? "
                "WHERE status='OPEN' AND acknowledged=0", (stamp, stamp),
            )
            acknowledged_count = max(0, int(cursor.rowcount or 0))
            services.close_incident_if_resolved(db)
        return {"ok": True, "acknowledged_count": acknowledged_count, **services.incident_status()}

    @router.post("/api/incidents/siren-off", dependencies=[Depends(services.require_admin)])
    def silence_incident_sirens() -> dict[str, Any]:
        command = getattr(services, "silence_incident_sirens", None)
        if command is not None:
            return command()
        stamp = services.now_business()
        with services.db_session() as db:
            cursor = db.execute(
                "UPDATE incidents SET siren_until=0, updated_at=? WHERE status='OPEN' AND siren_until>0", (stamp,)
            )
            stopped_count = max(0, int(cursor.rowcount or 0))
        return {"ok": True, "stopped_count": stopped_count, **services.incident_status()}

    return router
