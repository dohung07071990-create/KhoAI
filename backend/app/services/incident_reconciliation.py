"""Periodic reconciliation of persisted incidents against detector health."""
from __future__ import annotations

from typing import Any, Callable


class IncidentReconciliationService:
    """Close resolved incidents only when detector state is explicitly safe.

    Detector access and database operations are injected by the composition root
    so this service remains independent from FastAPI and ``main.py``.
    """

    def __init__(self, db_session: Callable[[], Any],
                 detector_state: Callable[[], str],
                 detector_provider: Callable[[], Any],
                 close_incident_if_resolved: Callable[[Any], None]) -> None:
        self.db_session = db_session
        self.detector_state = detector_state
        self.detector_provider = detector_provider
        self.close_incident_if_resolved = close_incident_if_resolved

    def reconcile_open_incidents(self) -> None:
        if self.detector_state() != "SAFE":
            return
        try:
            detector = self.detector_provider()
            status = detector.status()
            if not bool(status.get("anti_theft_enabled", True)):
                return
        except Exception:
            # A missing/unhealthy detector must never cause an incident to close.
            return
        with self.db_session() as db:
            self.close_incident_if_resolved(db)
