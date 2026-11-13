"""Persistence and incident routing for events emitted by the external USB camera."""
from __future__ import annotations

import json
import sqlite3
from typing import Any, Callable


class CameraEventSyncService:
    """Persist detector events and route new events into the incident store.

    Dependencies are injected so this service does not import the FastAPI
    composition root or own detector/worker lifecycle.
    """

    def __init__(self, db_session: Callable[[], Any], now_business: Callable[[], str],
                 open_incident: Callable[..., str], record_incident_event: Callable[..., None],
                 link_event_to_incident: Callable[..., None],
                 health_incident_type: Callable[..., str],
                 close_health_incidents: Callable[..., None],
                 close_incident_if_resolved: Callable[..., None]) -> None:
        self.db_session = db_session
        self.now_business = now_business
        self.open_incident = open_incident
        self.record_incident_event = record_incident_event
        self.link_event_to_incident = link_event_to_incident
        self.health_incident_type = health_incident_type
        self.close_health_incidents = close_health_incidents
        self.close_incident_if_resolved = close_incident_if_resolved

    def sync_events(self, events: list[dict[str, Any]]) -> None:
        """Persist detector events idempotently and update related incidents."""
        if not events:
            return
        with self.db_session() as db:
            for event in events:
                source_time = str(event.get("event_at") or "")
                if not source_time:
                    continue
                event_type = str(event.get("type") or "camera_event")
                severity_raw = str(event.get("severity", "medium")).lower()
                severity = ("severe" if severity_raw in {"high", "critical", "severe"}
                            else "warning" if severity_raw in {"medium", "warning"} else "info")
                source_id = str(event.get("event_id") or f"{event_type}:{event.get('track_id')}:{source_time}")
                details = {"source": "usb_external", "camera_event_at": source_time,
                           "track_id": event.get("track_id"), "zone": "external", **event}
                existing = db.execute(
                    "SELECT id, details_json FROM security_events WHERE source_event_id=?", (source_id,)
                ).fetchone()
                is_new_event = existing is None
                details_json = json.dumps(details, ensure_ascii=False)
                if existing:
                    # Evidence metadata can arrive shortly after the initial detector event.
                    try:
                        old_details = json.loads(existing["details_json"] or "{}")
                    except (TypeError, ValueError):
                        old_details = {}
                    if ((event.get("evidence_url") and not old_details.get("evidence_url"))
                            or event.get("evidence_filename")):
                        old_details.update(details)
                        merged_details_json = json.dumps(old_details, ensure_ascii=False)
                        db.execute("UPDATE security_events SET details_json=? WHERE id=?",
                                   (merged_details_json, existing["id"]))
                        db.execute("UPDATE incident_events SET details_json=? WHERE source_event_id=?",
                                   (merged_details_json, source_id))
                else:
                    db.execute("""INSERT INTO security_events
                        (event_at,event_type,track_id,severity,message,details_json,source_event_id)
                        VALUES(?,?,?,?,?,?,?)""",
                        (source_time, event_type, event.get("track_id"), severity,
                         str(event.get("message") or "Sự kiện camera USB ngoài."), details_json, source_id))

                if not is_new_event:
                    continue
                alarm_event_state = str(event.get("state", event.get("alarm_state", ""))).upper()
                is_alarm = event_type == "alarm_state_changed" and alarm_event_state == "ALARM"
                is_intrusion = (event_type in {"unauthorized_entry", "wrong_zone", "anonymous_zone_alarm"}
                                and severity == "severe")
                is_intrusion_attempt = event_type == "intrusion_attempt_aborted"
                is_health_start = event_type in {
                    "camera_offline", "camera_unstable", "ai_model_unavailable", "ai_processing_stalled"
                }
                is_health_alarm = is_alarm and str(event.get("reason", "")) == "health_fault"

                if is_health_start:
                    incident_id = self.open_incident(
                        db, event, self.health_incident_type(event_type=event_type), start_siren=False)
                    self.record_incident_event(db, incident_id, event, source_id)
                    self.link_event_to_incident(db, source_id, incident_id)
                elif is_health_alarm:
                    incident_id = self.open_incident(
                        db, event, self.health_incident_type(health_reason=event.get("health_reason")),
                        start_siren=True)
                    self.record_incident_event(db, incident_id, event, source_id)
                    self.link_event_to_incident(db, source_id, incident_id)
                elif is_intrusion_attempt:
                    incident_id = self.open_incident(db, event, "intrusion_attempt", start_siren=False)
                    self.record_incident_event(db, incident_id, event, source_id)
                    self.link_event_to_incident(db, source_id, incident_id)
                    stamp = self.now_business()
                    db.execute("""UPDATE incidents SET status='CLOSED',closed_at=?,updated_at=?
                        WHERE incident_id=? AND status='OPEN'""", (stamp, stamp, incident_id))
                elif is_alarm or is_intrusion:
                    incident_id = self.open_incident(db, event, "intrusion", start_siren=True)
                    self.record_incident_event(db, incident_id, event, source_id)
                    self.link_event_to_incident(db, source_id, incident_id)
                elif event_type in {"camera_recovered", "system_health_recovered"}:
                    self.close_health_incidents(db, event)
                elif event_type == "alarm_state_changed" and alarm_event_state == "SAFE":
                    self.close_incident_if_resolved(db)
