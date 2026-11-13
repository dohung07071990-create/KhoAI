"""Authenticated ingestion of compatibility events from external camera clients."""
from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends

from ..schemas import SecurityEventInput
from ..services.external_event_processor import process_external_camera_event


def create_external_event_router(services: Any) -> APIRouter:
    router = APIRouter()

    def persist_external_alert(
        level: str, kind: str, zone: str | None, message: str,
        uid: str | None = None, details: dict[str, Any] | None = None,
    ) -> None:
        """Delegate deduplicated alert persistence to the injected service."""
        persist = getattr(services, "persist_external_alert", None)
        if persist is not None:
            persist(level, kind, zone, message, uid, details)
            return
        # Backward-compatible fallback for isolated router consumers.
        with services.db_session() as db:
            rows = db.execute(
                "SELECT id, details_json FROM security_events WHERE event_type=? "
                "AND severity IN ('warning','severe') ORDER BY id DESC LIMIT 100", (kind,),
            ).fetchall()
            for row in rows:
                if db.execute("SELECT 1 FROM acknowledged_events WHERE event_id=?", (row["id"],)).fetchone():
                    continue
                try:
                    info = json.loads(row["details_json"] or "{}")
                except (TypeError, ValueError):
                    info = {}
                if info.get("zone") == zone and info.get("uid") == uid:
                    return
            db.execute(
                "INSERT INTO security_events(event_at,event_type,track_id,severity,message,details_json) "
                "VALUES(?,?,?,?,?,?)",
                (services.now_business(), kind, None, level, message,
                 json.dumps({"zone": zone, "uid": uid, **(details or {})}, ensure_ascii=False)),
            )

    @router.post("/api/events", dependencies=[Depends(services.require_admin)])
    def ingest_doan2_camera_event(payload: SecurityEventInput) -> dict[str, Any]:
        return process_external_camera_event(payload, services, persist_external_alert)

    return router
