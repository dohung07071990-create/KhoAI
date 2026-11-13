"""Regression tests for the single stable-camera predicate and same-handle recovery."""
import pytest

from ai.person_detector import CameraDetector


def _detector_with_clock(monkeypatch, now=100.0):
    import ai.person_detector as pd
    clock = {"now": float(now)}
    monkeypatch.setattr(pd.time, "monotonic", lambda: clock["now"])
    detector = CameraDetector(model=object())
    detector._started_at = 1.0
    detector._last_raw_at = float("-inf")
    return detector, clock


def _publish_at(detector, clock, at):
    clock["now"] = float(at)
    detector._publish_raw(__import__("numpy").zeros((8, 8, 3), dtype="uint8"))


def _publish_stable_run(detector, clock, start):
    for offset in (0.0, 0.25, 0.50, 0.75, 1.0):
        _publish_at(detector, clock, start + offset)


def test_stable_predicate_enforces_duration_frame_count_gap_and_staleness(monkeypatch):
    import ai.person_detector as pd
    detector, clock = _detector_with_clock(monkeypatch)
    detector._camera_frame_times.extend([99.0, 99.5, 100.0])
    detector._last_raw_at = 100.0
    assert detector._camera_stream_stable_locked(100.0)

    detector._camera_frame_times.clear()
    detector._camera_frame_times.extend([99.0, 99.5, 99.999])
    detector._last_raw_at = 99.999
    assert not detector._camera_stream_stable_locked(99.999)  # less than 1 second

    detector._camera_frame_times.clear()
    detector._camera_frame_times.extend([99.0, 99.5001, 100.0])
    detector._last_raw_at = 100.0
    assert not detector._camera_stream_stable_locked(100.0)  # gap > 0.5 seconds

    detector._camera_frame_times.clear()
    detector._camera_frame_times.extend([99.0, 99.5])
    detector._last_raw_at = 100.0
    assert not detector._camera_stream_stable_locked(100.0)  # fewer than 3 frames

    detector._camera_frame_times.clear()
    detector._camera_frame_times.extend([99.0, 99.5, 100.0])
    detector._last_raw_at = 100.0
    assert not detector._camera_stream_stable_locked(100.0 + pd.CAMERA_FRAME_STALE_SECONDS)


def test_status_and_rfid_ticket_use_the_same_stable_camera_predicate(monkeypatch):
    detector, clock = _detector_with_clock(monkeypatch, 200.0)
    assert detector.status()["camera_ok"] is False
    with pytest.raises(RuntimeError, match="ổn định"):
        detector.create_rfid_ticket("AABBCCDD", "Worker", ["external_usb_zone"])

    _publish_at(detector, clock, 200.0)
    _publish_at(detector, clock, 200.5)
    assert detector.status()["camera_ok"] is False
    with pytest.raises(RuntimeError, match="ổn định"):
        detector.create_rfid_ticket("AABBCCDD", "Worker", ["external_usb_zone"])

    _publish_at(detector, clock, 201.0)
    assert detector.status()["camera_ok"] is True
    assert detector._camera_health is True
    ticket = detector.create_rfid_ticket("AABBCCDD", "Worker", ["external_usb_zone"])
    assert ticket["pending_binding"] is True

    clock["now"] = 204.1
    assert detector.status()["camera_ok"] is False
    with pytest.raises(RuntimeError, match="ổn định"):
        detector.create_rfid_ticket("11223344", "Worker", ["external_usb_zone"])


def test_same_capture_handle_recovers_after_stall_and_old_credentials_stay_revoked(monkeypatch):
    detector, clock = _detector_with_clock(monkeypatch)
    _publish_stable_run(detector, clock, 99.0)
    class SameHandle:
        def describe(self): return "same-test-camera-handle"
    handle = SameHandle()
    detector._camera_info = handle
    detector._last_frame_size = (640, 480)
    detector._authorized_tracks[7] = {
        "uid": "OLDUID", "at": 100.0, "allowed_zones": ["external_usb_zone"],
    }
    detector.create_rfid_ticket("OLDTICKET", "Old worker", ["external_usb_zone"])

    clock["now"] = 103.1
    assert detector._revoke_rfid_on_camera_stall(clock["now"]) is True
    assert detector._camera_health is False
    assert detector._authorized_tracks == {}
    assert detector._rfid_tickets == {}

    # Simulate cap.read() resuming on the same capture handle; no reopen is performed.
    _publish_stable_run(detector, clock, 103.1)
    assert detector._camera_info is handle
    assert detector._camera_health is True
    assert detector.status()["camera_ok"] is True
    assert detector._authorized_tracks == {}
    assert detector._rfid_tickets == {}
    assert [e["type"] for e in detector.get_events()].count("camera_recovered") == 1
    detector.create_rfid_ticket("NEWUID", "New worker", ["external_usb_zone"])


def test_intermittent_frame_bursts_do_not_recover_or_unlock_rfid(monkeypatch):
    detector, clock = _detector_with_clock(monkeypatch)
    _publish_stable_run(detector, clock, 99.0)
    clock["now"] = 103.1
    detector._revoke_rfid_on_camera_stall(clock["now"])
    assert detector._camera_health is False

    for start in (103.1, 104.2, 105.3):
        for offset in (0.0, 0.2, 0.4):
            _publish_at(detector, clock, start + offset)
        # Each burst is shorter than the 1-second stable window and separated by >0.5s.

    assert detector._camera_health is False
    assert detector.status()["camera_ok"] is False
    assert not any(e["type"] == "camera_recovered" for e in detector.get_events())
    with pytest.raises(RuntimeError, match="ổn định"):
        detector.create_rfid_ticket("AABBCCDD", "Worker", ["external_usb_zone"])


def test_offline_and_recovered_events_balance_across_multiple_stalls(monkeypatch):
    detector, clock = _detector_with_clock(monkeypatch)
    _publish_stable_run(detector, clock, 99.0)
    for cycle in range(2):
        stall_at = clock["now"] + 3.1
        clock["now"] = stall_at
        assert detector._revoke_rfid_on_camera_stall(stall_at)
        _publish_stable_run(detector, clock, stall_at)

    types = [event["type"] for event in detector.get_events()]
    assert types.count("camera_offline") == 2
    assert types.count("camera_recovered") == 2


def test_startup_grace_does_not_emit_unpaired_camera_recovery_event(monkeypatch):
    detector, clock = _detector_with_clock(monkeypatch, 100.0)
    detector._started_at = 99.5
    detector._set_camera_health(False, "startup still waiting")
    assert not any(e["type"] == "camera_offline" for e in detector.get_events())
    _publish_stable_run(detector, clock, 100.0)
    types = [event["type"] for event in detector.get_events()]
    assert types.count("camera_offline") == 0
    assert types.count("camera_recovered") == 0
