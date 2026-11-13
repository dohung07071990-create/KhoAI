"""Read and normalize the detector's externally visible alarm state."""
from __future__ import annotations

from typing import Any, Callable


class DetectorStateReader:
    """Resolve the detector's alarm state without coupling to the AI package."""

    def __init__(self, detector_provider: Callable[[], Any]) -> None:
        self.detector_provider = detector_provider

    def get_state(self) -> str:
        try:
            detector = self.detector_provider()
            status = detector.status()
            if not bool(status.get("anti_theft_enabled", True)):
                return "DISARMED"
            return str(status.get("alarm_state", "UNKNOWN")).upper()
        except Exception:
            return "UNKNOWN"
