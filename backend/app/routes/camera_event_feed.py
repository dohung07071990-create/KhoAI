"""Read-only USB camera event feed endpoint."""
from __future__ import annotations

from typing import Any, Protocol

from fastapi import APIRouter, Depends, Query, Request


class CameraEventFeedServices(Protocol):
    db_session: Any
    require_session: Any
    mask_uid_payload: Any


def create_camera_event_feed_router(services: CameraEventFeedServices) -> APIRouter:
    router = APIRouter()

    @router.get("/api/camera/events", dependencies=[Depends(services.require_session)])
    def camera_events(request: Request, limit: int = Query(default=30, ge=1, le=100)) -> list[dict[str, Any]]:
        with services.db_session() as db:
            rows = db.execute(
                "SELECT event_at,event_type,track_id,severity,message,details_json "
                "FROM security_events WHERE source_event_id IS NOT NULL ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        result = []
        for row in rows:
            details = json_loads(row["details_json"])
            result.append({**details, "type": row["event_type"], "event_at": row["event_at"],
                           "track_id": row["track_id"], "severity": row["severity"], "message": row["message"]})
        if getattr(request.state, "khoai_role", None) == "admin":
            return result
        return services.mask_uid_payload(result)

    return router


def json_loads(value: str | None) -> dict[str, Any]:
    import json
    parsed = json.loads(value or "{}")
    return parsed if isinstance(parsed, dict) else {}
