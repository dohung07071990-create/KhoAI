"""Security regressions for RFID identity continuity and camera outages."""
import pytest

from ai.person_detector import CameraDetector


def _live_detector(monkeypatch, now=100.0):
    import ai.person_detector as pd
    clock = {"now": float(now)}
    monkeypatch.setattr(pd.time, "monotonic", lambda: clock["now"])
    detector = CameraDetector(model=object())
    detector._camera_health = True
    detector._last_raw_at = clock["now"]
    detector._camera_frame_times.extend([clock["now"] - 1.0, clock["now"] - 0.5, clock["now"]])
    detector._track_state[7] = {
        "inside": True, "last_seen_at": clock["now"],
        "last_box": (100.0, 100.0, 200.0, 300.0),
    }
    return detector, clock


def test_authorization_is_never_handed_to_spatially_near_new_track(monkeypatch):
    detector, clock = _live_detector(monkeypatch)
    detector._authorized_tracks[7] = {
        "uid": "AABBCCDD", "at": clock["now"],
        "allowed_zones": ["external_usb_zone"],
    }
    detector._track_state[7]["last_seen_at"] = clock["now"]
    detector._update_tracks([{"id": 8, "box": (101, 100, 201, 300), "raw_inside": True}], clock["now"] + 0.1)
    assert 7 in detector._authorized_tracks
    assert 8 not in detector._authorized_tracks


def test_association_requires_one_use_ticket_and_live_track(monkeypatch):
    detector, clock = _live_detector(monkeypatch)
    with pytest.raises(ValueError, match="ticket"):
        detector.associate_card(7, "AABBCCDD", allowed_zones=["external_usb_zone"])

    detector.create_rfid_ticket("AABBCCDD", "Worker", ["external_usb_zone"], ttl_seconds=20)
    result = detector.associate_card(7, "AABBCCDD", allowed_zones=["external_usb_zone"])
    assert result["associated"] is True
    assert result["ticket_consumed"] is True
    assert 7 in detector._authorized_tracks
    assert not detector.has_rfid_ticket("AABBCCDD")


def test_association_rejects_stale_track_and_keeps_ticket_pending(monkeypatch):
    detector, clock = _live_detector(monkeypatch)
    detector.create_rfid_ticket("AABBCCDD", "Worker", ["external_usb_zone"], ttl_seconds=20)
    clock["now"] += 2.0
    with pytest.raises(ValueError, match="Track"):
        detector.associate_card(7, "AABBCCDD", allowed_zones=["external_usb_zone"])
    assert detector.has_rfid_ticket("AABBCCDD")
    assert 7 not in detector._authorized_tracks


def test_camera_outage_revokes_pending_and_active_rfid_even_if_short(monkeypatch):
    import ai.person_detector as pd
    clock = {"now": 100.0}
    monkeypatch.setattr(pd.time, "monotonic", lambda: clock["now"])
    detector = CameraDetector(model=object())
    detector._last_raw_at = 99.5
    detector._camera_frame_times.extend([98.5, 99.0, 99.5])
    detector._track_state[7] = {"inside": True, "last_seen_at": 99.5,
                                "last_box": (100, 100, 200, 300)}
    detector._authorized_tracks[7] = {"uid": "AABBCCDD", "at": 99.0,
                                      "allowed_zones": ["external_usb_zone"]}
    detector.create_rfid_ticket("11223344", "Worker", ["external_usb_zone"])
    detector._set_camera_health(False, "offline")
    assert detector._authorized_tracks == {}
    assert detector._rfid_tickets == {}
    clock["now"] = 102.0
    detector._set_camera_health(True)
    assert detector._track_state_preservation_age == 2.5
    assert detector._track_state_preservation_last == "preserved_short_reconnect"
    assert detector._authorized_tracks == {}
    assert detector._rfid_tickets == {}


def test_outage_duration_starts_at_last_good_frame_not_health_transition(monkeypatch):
    import ai.person_detector as pd
    clock = {"now": 100.0}
    monkeypatch.setattr(pd.time, "monotonic", lambda: clock["now"])
    detector = CameraDetector(model=object())
    detector._last_raw_at = 99.0
    detector._set_camera_health(False, "offline")
    # Health transition happened at 100, but the last good frame was at 99.
    clock["now"] = 102.2
    detector._set_camera_health(True)
    assert detector._track_state_preservation_age == pytest.approx(3.2)
    assert detector._track_state_preservation_last == "reset_after_long_outage"


def test_stop_clears_pending_rfid_tickets(monkeypatch):
    detector, _clock = _live_detector(monkeypatch)
    detector.create_rfid_ticket("AABBCCDD", "Worker", ["external_usb_zone"])
    detector._authorized_tracks[7] = {"uid": "AABBCCDD", "at": 100.0,
                                      "allowed_zones": ["external_usb_zone"]}
    detector.stop()
    assert detector._rfid_tickets == {}
    assert detector._authorized_tracks == {}


def test_no_ticket_can_be_created_while_camera_known_offline(monkeypatch):
    detector, _clock = _live_detector(monkeypatch)
    detector._camera_health = False
    with pytest.raises(RuntimeError, match="Camera"):
        detector.create_rfid_ticket("AABBCCDD", "Worker", ["external_usb_zone"])


def test_authorization_revoked_when_track_disappears_beyond_short_gap(monkeypatch):
    detector, clock = _live_detector(monkeypatch)
    detector._authorized_tracks[7] = {
        "uid": "AABBCCDD", "at": clock["now"],
        "allowed_zones": ["external_usb_zone"],
    }
    detector._update_tracks([], clock["now"] + 0.8)
    assert 7 not in detector._authorized_tracks
    event = next(e for e in detector.get_events() if e["type"] == "authorization_revoked")
    assert event["reason"] == "track_lost"


def test_track_authorization_ttl_is_capped_at_one_minute():
    import ai.person_detector as pd
    assert pd.AUTH_MAX_SECONDS <= 60.0
