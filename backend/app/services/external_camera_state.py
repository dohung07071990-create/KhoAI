"""In-memory state reported by compatibility external-camera clients.

The store deliberately contains presentation/status data only. It does not
make access-control or alarm decisions.
"""
from __future__ import annotations

from copy import deepcopy
from threading import RLock
from typing import Any


class ExternalCameraState:
    def __init__(self, initial: dict[str, Any] | None = None) -> None:
        self._lock = RLock()
        self._state: dict[str, Any] = initial if initial is not None else {
            "outside": {"people": 0, "max_seconds": 0, "ts": None},
            "inside": [],
        }

    @property
    def data(self) -> dict[str, Any]:
        """Return the legacy mutable mapping for compatibility consumers."""
        return self._state

    def update_outside(self, people: int, max_seconds: float, timestamp: str) -> None:
        with self._lock:
            self._state["outside"] = {
                "people": people,
                "max_seconds": max_seconds,
                "ts": timestamp,
            }

    def update_inside(self, people: list[dict[str, Any]]) -> None:
        with self._lock:
            self._state["inside"] = people

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return deepcopy(self._state)
