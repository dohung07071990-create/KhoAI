"""Resolve the public alarm level from live detector and incident state."""
from __future__ import annotations

import logging
from typing import Any, Callable


class AlarmLevelResolver:
    """Map Decision Engine state and incident latch to the API alarm vocabulary."""

    VALID_STATES = {"SAFE", "WARNING", "ALARM", "REVIEW", "PENDING"}

    def __init__(
        self,
        detector_provider: Callable[[], Any],
        incident_status_provider: Callable[[], dict[str, Any]],
        logger: logging.Logger,
    ) -> None:
        self.detector_provider = detector_provider
        self.incident_status_provider = incident_status_provider
        self.logger = logger

    def get_level(self) -> str:
        """Return off/warning/severe; detector failures remain unknown."""
        try:
            status = self.detector_provider().status()
            state = str(status.get("alarm_state", "UNKNOWN")).upper()
            if state not in self.VALID_STATES:
                return "unknown"
        except Exception:
            self.logger.exception("Không đọc được trạng thái Decision Engine")
            return "unknown"

        incident = self.incident_status_provider()
        if incident.get("latched"):
            return "severe"
        if state == "ALARM":
            return "severe"
        if state in {"WARNING", "PENDING"}:
            return "warning"
        return "off"
