"""Read-only incident timeline endpoint."""
from __future__ import annotations

import json
from typing import Any, Protocol

from fastapi import APIRouter, Depends, HTTPException, Request


class IncidentTimelineServices(Protocol):
    db_session: Any
    require_session: Any
    mask_uid_payload: Any


def create_incident_timeline_router(services: IncidentTimelineServices) -> APIRouter:
    router = APIRouter()

    @router.get("/api/incidents/{incident_id}/timeline", dependencies=[Depends(services.require_session)])
    def incident_timeline(incident_id: str, request: Request) -> dict[str, Any]:
        with services.db_session() as db:
            incident = db.execute("SELECT * FROM incidents WHERE incident_id=?", (incident_id,)).fetchone()
            if not incident:
                raise HTTPException(status_code=404, detail="Không tìm thấy incident.")
            rows = db.execute(
                "SELECT event_type,track_id,event_at,details_json FROM incident_events "
                "WHERE incident_id=? ORDER BY event_at ASC,id ASC", (incident_id,),
            ).fetchall()
        events = []
        for row in rows:
            try:
                details = json.loads(row["details_json"] or "{}")
                if not isinstance(details, dict):
                    details = {}
            except (TypeError, ValueError):
                details = {}
            events.append({"type": row["event_type"], "track_id": row["track_id"],
                           "event_at": row["event_at"], "details": details,
                           "explanation": details.get("reason") or details.get("message") or row["event_type"]})
        result = {"incident": dict(incident), "events": events}
        return result if getattr(request.state, "khoai_role", None) == "admin" else services.mask_uid_payload(result)

    return router
