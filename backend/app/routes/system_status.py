"""Authenticated dashboard system-status endpoint."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends


def create_system_status_router(services: Any) -> APIRouter:
    router = APIRouter()

    @router.get("/api/status", dependencies=[Depends(services.require_session)])
    def integrated_status() -> dict[str, Any]:
        today = services.today_business()
        with services.db_session() as db:
            card_count = db.execute("SELECT COUNT(*) FROM cards").fetchone()[0]
            scan_count = db.execute(
                "SELECT COUNT(*) FROM access_logs WHERE substr(event_at,1,10)=?", (today,)
            ).fetchone()[0]
            open_alerts = db.execute("""SELECT COUNT(*) FROM security_events e
                WHERE e.severity IN ('warning','severe')
                AND e.id NOT IN (SELECT event_id FROM acknowledged_events)""").fetchone()[0]
            device = db.execute(
                "SELECT * FROM device_heartbeats ORDER BY last_seen DESC LIMIT 1"
            ).fetchone()
            orders = db.execute(
                "SELECT COALESCE(SUM(boxes),0) FROM pickup_orders WHERE day=?", (today,)
            ).fetchone()[0]

        online = False
        if device:
            try:
                online = (services.now_datetime() - datetime.fromisoformat(device["last_seen"])).total_seconds() < 15
            except (ValueError, TypeError):
                online = False

        outside = {"people": 0, "scanned": services.scans_today_allowed(), "max_seconds": 0.0, "ts": None}
        decision_tracks: dict[str, Any] = {}
        try:
            camera_state = services.detector_provider().status()
            decision_tracks = camera_state.get("decision_tracks", {}) or {}
            outside["people"] = int(camera_state.get("people_in_zone", 0))
            outside["max_seconds"] = max(
                (float(item.get("elapsed_seconds", 0)) for item in decision_tracks.values()),
                default=0.0,
            )
            outside["ts"] = camera_state.get("last_frame_at")
        except Exception:
            services.logger.exception("Không lấy được số liệu camera USB cho dashboard")
        outside["real_minutes"] = round(float(outside["max_seconds"]) / 60.0, 1)
        incident_state = services.incident_status()
        return {
            "device_online": online,
            "alarm": services.current_alarm_level(),
            "cards": card_count,
            "scans_today": scan_count,
            "open_alerts": open_alerts,
            "incident": incident_state,
            "authorized_boxes_today": orders,
            "time_scale": 1,
            "time_scale_mode": "REAL",
            "outside": outside,
            "inside": services.external_camera_state()["inside"],
            "decision_tracks": decision_tracks,
        }

    return router
