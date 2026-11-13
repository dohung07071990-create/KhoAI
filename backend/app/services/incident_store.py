"""Persistence facade for incident records and their source events.

This module deliberately contains no FastAPI or application-main imports.
"""
from __future__ import annotations

import sqlite3
from typing import Any, Callable

from .incident_event_store import IncidentEventStore
from .incident_lifecycle import IncidentLifecycleService


class IncidentStore:
    def __init__(self, now_business: Callable[[], str], cooldown_seconds: float,
                 siren_seconds: int, detector_state: Callable[[], str]):
        self.now_business = now_business
        self.cooldown_seconds = cooldown_seconds
        self.siren_seconds = siren_seconds
        self.detector_state = detector_state
        self.event_store = IncidentEventStore(now_business, cooldown_seconds)
        self.lifecycle = IncidentLifecycleService(
            now_business, cooldown_seconds, siren_seconds, detector_state
        )

    def open_incident(self, db: sqlite3.Connection, event: dict[str, Any],
                      incident_type: str = "intrusion", *, start_siren: bool = True) -> str:
        return self.lifecycle.open_incident(db, event, incident_type, start_siren=start_siren)

    def record_event(self, db: sqlite3.Connection, incident_id: str,
                     event: dict[str, Any], source_id: str) -> None:
        self.event_store.record_event(db, incident_id, event, source_id)

    @staticmethod
    def link_event(db: sqlite3.Connection, source_id: str, incident_id: str) -> None:
        IncidentEventStore.link_event(db, source_id, incident_id)

    def close_resolved(self, db: sqlite3.Connection) -> None:
        self.lifecycle.close_resolved(db)
