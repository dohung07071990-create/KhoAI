"""Focused security regressions for dev.23.3 RFID hardening."""
import pytest

from ai.person_detector import CameraDetector


ROI = ((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0))
BOX_A = (100.0, 100.0, 200.0, 300.0)


def _clocked_detector(monkeypatch, now=100.0, auto_bind=False):
    import ai.person_detector as pd
    clock = {"now": float(now)}
    monkeypatch.setattr(pd.time, "monotonic", lambda: clock["now"])
    monkeypatch.setattr(pd, "RFID_AUTO_BIND_ENABLED", auto_bind)
    detector = CameraDetector(model=object())
    detector._camera_health = True
    detector._last_raw_at = clock["now"]
    detector._camera_frame_times.extend([clock["now"] - 1.0, clock["now"] - 0.5, clock["now"]])
    detector._last_frame_size = (640, 480)
    detector.rfid_entry_roi = ROI
    return detector, clock


def _seed_candidate(detector, track_id=7, box=BOX_A, now=100.0):
    detector._last_detection_at = now
    detector._last_detections = [{"id": track_id, "box": box}]
    detector._track_state[track_id] = {
        "inside": False, "last_seen_at": now, "last_box": box,
    }


def test_watchdog_stale_frame_revokes_ticket_and_authorization_even_if_health_true(monkeypatch):
    detector, clock = _clocked_detector(monkeypatch)
    detector._authorized_tracks[7] = {
        "uid": "AABBCCDD", "at": 99.0, "allowed_zones": ["external_usb_zone"],
    }
    detector.create_rfid_ticket("11223344", "Worker", ["external_usb_zone"])
    assert detector._camera_health is True
    clock["now"] = 103.1

    assert detector._revoke_rfid_on_camera_stall(clock["now"]) is True
    assert detector._camera_health is False
    assert detector._authorized_tracks == {}
    assert detector._rfid_tickets == {}
    assert any(event["type"] == "camera_offline" for event in detector.get_events())


def test_old_ticket_cannot_authorize_new_person_after_camera_recovery(monkeypatch):
    detector, clock = _clocked_detector(monkeypatch)
    detector.create_rfid_ticket("11223344", "Worker", ["external_usb_zone"])
    clock["now"] = 104.0
    detector._revoke_rfid_on_camera_stall(clock["now"])
    clock["now"] = 105.0
    detector._last_raw_at = 105.0
    detector._set_camera_health(True)
    detector._track_state[99] = {"inside": True, "last_seen_at": 105.0, "last_box": BOX_A}

    with pytest.raises(ValueError, match="ticket"):
        detector.associate_card(99, "11223344", allowed_zones=["external_usb_zone"])
    assert 99 not in detector._authorized_tracks


def test_auto_binding_is_disabled_by_default_and_requires_manual_association(monkeypatch):
    detector, clock = _clocked_detector(monkeypatch, auto_bind=False)
    _seed_candidate(detector, now=clock["now"])
    ticket = detector.create_rfid_ticket("AABBCCDD", "Worker", ["external_usb_zone"])
    assert ticket["manual_confirmation_required"] is True
    detector._try_bind_rfid_tickets([{"id": 7, "box": BOX_A}], 100.4, (640, 480))
    assert detector._authorized_tracks == {}
    assert detector.has_rfid_ticket("AABBCCDD")


def test_person_already_in_roi_at_swipe_is_bound_after_stability_when_opted_in(monkeypatch):
    detector, clock = _clocked_detector(monkeypatch, auto_bind=True)
    _seed_candidate(detector, track_id=7, now=clock["now"])
    detector.create_rfid_ticket("AABBCCDD", "Worker", ["external_usb_zone"])

    detector._try_bind_rfid_tickets([{"id": 7, "box": BOX_A}], 100.0, (640, 480))
    assert 7 not in detector._authorized_tracks
    clock["now"] = 100.31
    detector._try_bind_rfid_tickets([{"id": 7, "box": BOX_A}], 100.31, (640, 480))

    assert detector._authorized_tracks[7]["uid"] == "AABBCCDD"
    assert not detector.has_rfid_ticket("AABBCCDD")


def test_two_people_in_roi_at_swipe_require_manual_confirmation(monkeypatch):
    detector, clock = _clocked_detector(monkeypatch, auto_bind=True)
    detector._last_detection_at = clock["now"]
    detector._last_detections = [
        {"id": 7, "box": BOX_A}, {"id": 8, "box": (250, 100, 350, 300)},
    ]
    detector.create_rfid_ticket("AABBCCDD", "Worker", ["external_usb_zone"])
    detector._try_bind_rfid_tickets([
        {"id": 7, "box": BOX_A}, {"id": 8, "box": (250, 100, 350, 300)},
    ], 100.5, (640, 480))

    assert detector._authorized_tracks == {}
    assert detector.has_rfid_ticket("AABBCCDD")
    assert detector._rfid_tickets["AABBCCDD"]["auto_bind_blocked"] is True


def test_new_person_entering_roi_after_swipe_blocks_auto_binding(monkeypatch):
    detector, clock = _clocked_detector(monkeypatch, auto_bind=True)
    _seed_candidate(detector, track_id=7, now=clock["now"])
    detector.create_rfid_ticket("AABBCCDD", "Worker", ["external_usb_zone"])
    detector._try_bind_rfid_tickets([
        {"id": 7, "box": BOX_A}, {"id": 8, "box": (250, 100, 350, 300)},
    ], 100.1, (640, 480))

    assert detector._authorized_tracks == {}
    assert detector._rfid_tickets["AABBCCDD"]["auto_bind_blocked"] is True


def test_authorization_expires_at_absolute_60_second_cap_without_renewal(monkeypatch):
    detector, clock = _clocked_detector(monkeypatch)
    detector._authorized_tracks[7] = {
        "uid": "AABBCCDD", "at": 100.0, "allowed_zones": ["external_usb_zone"],
    }
    clock["now"] = 160.0
    detector._apply_events([], [], clock["now"])
    assert 7 not in detector._authorized_tracks
    assert any(e["type"] == "authorization_expired" and e.get("reason") == "auth_max_seconds"
               for e in detector.get_events())


def test_strong_overlap_with_another_track_revokes_rfid_authorization(monkeypatch):
    detector, clock = _clocked_detector(monkeypatch)
    detector._authorized_tracks[7] = {
        "uid": "AABBCCDD", "at": clock["now"], "allowed_zones": ["external_usb_zone"],
    }
    detections = [
        {"id": 7, "box": (100, 100, 200, 300), "raw_inside": True},
        {"id": 8, "box": (110, 110, 210, 310), "raw_inside": True},
    ]
    detector._update_tracks(detections, clock["now"] + 0.1)

    assert 7 not in detector._authorized_tracks
    event = next(e for e in detector.get_events() if e["type"] == "authorization_revoked")
    assert event["reason"] == "track_overlap"
    assert event["conflicting_track_id"] == 8


def test_short_track_loss_does_not_restore_authorization_on_same_id(monkeypatch):
    detector, clock = _clocked_detector(monkeypatch)
    detector._authorized_tracks[7] = {
        "uid": "AABBCCDD", "at": clock["now"], "allowed_zones": ["external_usb_zone"],
    }
    detector._track_state[7] = {"inside": True, "last_seen_at": clock["now"], "last_box": BOX_A}
    detector._update_tracks([], clock["now"] + 0.8)
    assert 7 not in detector._authorized_tracks
    detector._update_tracks([{"id": 7, "box": BOX_A, "raw_inside": True}], clock["now"] + 0.9)
    assert 7 not in detector._authorized_tracks


def test_decision_engine_entry_grace_remains_eight_seconds_by_default():
    import ai.person_detector as pd
    assert pd.ENTRY_GRACE_SECONDS == pytest.approx(8.0)
    assert pd.AUTH_MAX_SECONDS <= 60.0
    assert pd.RFID_TRACK_AUTH_LOSS_SECONDS == pytest.approx(0.75)


def test_crossing_track_paths_revoke_authorization_even_without_current_box_overlap(monkeypatch):
    detector, clock = _clocked_detector(monkeypatch)
    detector._authorized_tracks[7] = {
        "uid": "AABBCCDD", "at": clock["now"], "allowed_zones": ["external_usb_zone"],
    }
    detector._track_state[7] = {"inside": True, "last_seen_at": 99.9, "last_box": (50, 50, 150, 150)}
    detector._track_state[8] = {"inside": True, "last_seen_at": 99.9, "last_box": (150, 50, 250, 150)}
    detections = [
        {"id": 7, "box": (150, 50, 250, 150), "raw_inside": True},
        {"id": 8, "box": (50, 50, 150, 150), "raw_inside": True},
    ]
    detector._update_tracks(detections, clock["now"] + 0.1)

    assert 7 not in detector._authorized_tracks
    event = next(e for e in detector.get_events() if e["type"] == "authorization_revoked")
    assert event["reason"] == "track_crossing"


def test_stale_frame_after_first_good_frame_is_not_hidden_by_startup_grace(monkeypatch):
    detector, clock = _clocked_detector(monkeypatch)
    detector._started_at = 99.0
    detector._authorized_tracks[7] = {
        "uid": "AABBCCDD", "at": 100.0, "allowed_zones": ["external_usb_zone"],
    }
    clock["now"] = 103.1

    assert detector._revoke_rfid_on_camera_stall(clock["now"]) is True
    assert detector._authorized_tracks == {}
    assert detector._camera_health is False


def test_anonymous_detection_in_roi_at_swipe_forces_manual_confirmation(monkeypatch):
    detector, clock = _clocked_detector(monkeypatch, auto_bind=True)
    detector._last_detection_at = clock["now"]
    detector._last_detections = [{"id": None, "box": BOX_A}]
    ticket = detector.create_rfid_ticket("AABBCCDD", "Worker", ["external_usb_zone"])

    assert ticket["manual_confirmation_required"] is True
    pending = detector.pending_rfid_tickets()[0]
    assert pending["manual_confirmation_required"] is True
    detector._try_bind_rfid_tickets([{"id": None, "box": BOX_A}], 100.4, (640, 480))
    assert detector._authorized_tracks == {}
