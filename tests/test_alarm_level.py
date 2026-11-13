from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest

from backend.app.services.alarm_level import AlarmLevelResolver


@pytest.mark.parametrize(
    ("state", "expected"),
    [("SAFE", "off"), ("WARNING", "warning"), ("PENDING", "warning"),
     ("ALARM", "severe"), ("REVIEW", "off"), ("unknown", "unknown")],
)
def test_alarm_level_maps_detector_state(state, expected):
    resolver = AlarmLevelResolver(
        detector_provider=lambda: SimpleNamespace(status=lambda: {"alarm_state": state}),
        incident_status_provider=lambda: {"latched": False},
        logger=logging.getLogger("test-alarm-level"),
    )
    assert resolver.get_level() == expected


def test_incident_latch_keeps_alarm_severe_even_when_detector_safe():
    resolver = AlarmLevelResolver(
        detector_provider=lambda: SimpleNamespace(status=lambda: {"alarm_state": "SAFE"}),
        incident_status_provider=lambda: {"latched": True},
        logger=logging.getLogger("test-alarm-level"),
    )
    assert resolver.get_level() == "severe"


def test_detector_provider_failure_returns_unknown(caplog):
    def fail():
        raise RuntimeError("detector unavailable")

    resolver = AlarmLevelResolver(
        detector_provider=fail,
        incident_status_provider=lambda: {"latched": False},
        logger=logging.getLogger("test-alarm-level"),
    )
    with caplog.at_level(logging.ERROR):
        assert resolver.get_level() == "unknown"
    assert "Không đọc được trạng thái Decision Engine" in caplog.text
