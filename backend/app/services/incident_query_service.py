"""Compatibility facade combining incident and security-alert read services."""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .incident_read_service import IncidentReadService
from .security_alert_query_service import SecurityAlertQueryService


class IncidentQueryService:
    """Preserve the previous public interface while delegating bounded read models."""

    def __init__(self, db_session: Callable[[], Any], mask_uid_payload: Callable[[Any], Any],
                 wall_time: Callable[[], float] | None = None) -> None:
        self.incident_reader = IncidentReadService(db_session, mask_uid_payload, wall_time)
        self.alert_reader = SecurityAlertQueryService(db_session, mask_uid_payload)

    @property
    def db_session(self):
        return self.incident_reader.db_session

    @db_session.setter
    def db_session(self, value):
        self.incident_reader.db_session = value
        self.alert_reader.db_session = value

    @property
    def mask_uid_payload(self):
        return self.incident_reader.mask_uid_payload

    @mask_uid_payload.setter
    def mask_uid_payload(self, value):
        self.incident_reader.mask_uid_payload = value
        self.alert_reader.mask_uid_payload = value

    def list_incidents(self, role: str | None, limit: int) -> list[dict[str, Any]]:
        return self.incident_reader.list_incidents(role, limit)

    def list_alerts(self, role: str | None, limit: int, severity: str) -> list[dict[str, Any]]:
        return self.alert_reader.list_alerts(role, limit, severity)
