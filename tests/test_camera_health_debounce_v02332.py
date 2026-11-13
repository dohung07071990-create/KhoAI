"""Regression tests for camera instability notification debounce and incident grouping."""
import logging

import numpy as np
import pytest


def _detector(monkeypatch, start=100.0):
    import ai.person_detector as pd
    clock = {"now": float(start)}
    monkeypatch.setattr(pd.time, "monotonic", lambda: clock["now"])
    detector = pd.CameraDetector(model=object())
    detector._started_at = 0.0
    detector.anti_theft_enabled = True
    detector._camera_health = True
    detector._last_raw_at = float(start)
    detector._last_processed_at = float(start)
    detector._camera_frame_times.extend([start - 1.0, start])
    return pd, detector, clock


def _frame(detector, clock, at):
    clock["now"] = float(at)
    detector._publish_raw(np.zeros((8, 8, 3), dtype=np.uint8))
    detector._last_processed_at = float(at)


def test_short_07s_hiccup_has_no_warning_or_events_but_rfid_stays_blocked(monkeypatch):
    pd, detector, clock = _detector(monkeypatch)
    with detector._lock:
        detector._camera_frame_times.clear()
        detector._camera_frame_times.extend([99.0, 99.5, 100.0])
        detector._authorized_tracks[7] = {
            "uid": "AUTHORIZED", "at": 100.0, "allowed_zones": ["external_usb_zone"]
        }
    detector.create_rfid_ticket("PENDING", "Worker", ["external_usb_zone"])
    detector._health_watchdog_tick(100.0)
    _frame(detector, clock, 100.7)  # next frame confirms a 0.7s gap
    detector._health_watchdog_tick(100.7)
    assert detector._health_failure_since == 100.5
    assert detector.alarm_state == "SAFE"
    assert not detector.get_events()
    assert detector._authorized_tracks == {}
    assert detector._rfid_tickets == {}
    with pytest.raises(RuntimeError, match="chưa có luồng frame ổn định"):
        detector.create_rfid_ticket("AABBCCDD", "Worker", ["external_usb_zone"])

    for at in (100.95, 101.20, 101.45, 101.70):
        _frame(detector, clock, at)
    detector._health_watchdog_tick(101.75)
    assert not detector.get_events()  # no orphaned recovery event
    assert detector._health_failure_since is None


def test_sustained_1fps_emits_one_start_and_one_recovery_and_logs_fps(monkeypatch, caplog):
    pd, detector, clock = _detector(monkeypatch)
    caplog.set_level(logging.WARNING)
    detector._health_watchdog_tick(100.0)
    for at in (101.0, 102.0, 103.0, 104.0):
        _frame(detector, clock, at)
        detector._health_watchdog_tick(at)
    events = detector.get_events()
    assert [event["type"] for event in events].count("camera_unstable") == 1
    assert detector.alarm_state == "WARNING"
    unstable = next(event for event in events if event["type"] == "camera_unstable")
    assert unstable["health_reason"] == "camera_unstable"
    assert unstable["max_frame_gap_seconds"] >= 0.99
    assert "capture_fps" in unstable
    assert any("khoảng 3 FPS trở lên" in record.message for record in caplog.records)

    for at in (104.25, 104.50, 104.75, 105.0, 105.25):
        _frame(detector, clock, at)
    detector._health_watchdog_tick(105.25)
    events = detector.get_events()
    assert [event["type"] for event in events].count("camera_unstable") == 1
    assert [event["type"] for event in events].count("system_health_recovered") == 1


def test_long_stall_has_only_offline_and_recovered_events(monkeypatch):
    pd, detector, clock = _detector(monkeypatch)
    detector._health_watchdog_tick(100.0)
    detector._health_watchdog_tick(101.0)
    detector._health_watchdog_tick(102.0)
    clock["now"] = 103.1
    detector._last_processed_at = 103.1
    assert detector._revoke_rfid_on_camera_stall(103.1)
    assert [e["type"] for e in detector.get_events()].count("camera_offline") == 1
    # Recovery requires a fresh continuous stable run; same capture path is used.
    for at in (103.1, 103.35, 103.6, 103.85, 104.1):
        _frame(detector, clock, at)
    types = [e["type"] for e in detector.get_events()]
    assert types.count("camera_unstable") == 0
    assert types.count("camera_offline") == 1
    assert types.count("camera_recovered") == 1
    assert types.count("system_health_recovered") == 0


def test_camera_unstable_maps_to_camera_outage_for_start_and_health_alarm():
    from backend.app.main import _health_incident_type
    assert _health_incident_type(event_type="camera_unstable") == "camera_outage"
    assert _health_incident_type(health_reason="camera_unstable") == "camera_outage"
    assert _health_incident_type(event_type="camera_offline") == "camera_outage"
    assert _health_incident_type(health_reason="ai_processing_stalled") == "ai_health"


def test_frontend_has_vietnamese_camera_unstable_labels():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    constants = (root / "frontend/core/constants.js").read_text(encoding="utf-8")
    history = (root / "frontend/dashboard/history-manager.js").read_text(encoding="utf-8")
    assert 'camera_unstable:"Camera USB không ổn định"' in constants
    assert 'camera_unstable:"Camera không ổn định"' in history


def test_1fps_reaches_alarm_at_30s_from_first_instability_observation(monkeypatch):
    pd, detector, clock = _detector(monkeypatch)
    detector._health_watchdog_tick(100.0)
    for at in range(101, 131):
        _frame(detector, clock, float(at))
        detector._health_watchdog_tick(float(at))
    assert detector._health_failure_since == 99.5
    assert detector.alarm_state == "ALARM"
    alarm_events = [e for e in detector.get_events()
                    if e["type"] == "alarm_state_changed" and e.get("alarm_state") == "ALARM"]
    assert len(alarm_events) == 1
    assert alarm_events[0].get("health_reason") == "camera_unstable"


def test_camera_unstable_and_offline_reuse_same_open_camera_incident():
    import sqlite3
    from backend.app.main import _open_incident

    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.execute("""CREATE TABLE incidents (
        incident_id TEXT PRIMARY KEY, incident_type TEXT, started_at TEXT, updated_at TEXT,
        status TEXT, acknowledged INTEGER, siren_until REAL, event_count INTEGER,
        summary_json TEXT, session_id TEXT, closed_at TEXT, acknowledged_at TEXT
    )""")
    db.execute("""CREATE TABLE incident_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT, incident_id TEXT, event_at TEXT,
        event_type TEXT, track_id INTEGER
    )""")
    first = _open_incident(db, {"type": "camera_unstable"}, "camera_outage", start_siren=False)
    second = _open_incident(db, {"type": "camera_offline"}, "camera_outage", start_siren=False)
    assert first == second
    assert db.execute("SELECT COUNT(*) FROM incidents WHERE status='OPEN'").fetchone()[0] == 1
    db.close()
