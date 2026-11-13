"""Bounded Track/Decision continuity across same-process camera reconnects."""
from ai.person_detector import CameraDetector


def _prime_active_track(detector):
    detector._track_state[41] = {
        "inside": True, "last_seen_at": 109.0,
        "last_box": (200.0, 100.0, 360.0, 420.0),
    }
    detector._authorized_tracks[41] = {
        "uid": "TEST-UID", "at": 109.0,
        "allowed_zones": ["external_usb_zone"],
    }
    detector._decision_engine.evaluate(
        [{"track_id": 41, "zone_id": "external_usb_zone", "inside": True,
          "position": [0.4, 0.6]}],
        armed=True, now=100.0,
    )
    result = detector._decision_engine.evaluate(
        [{"track_id": 41, "zone_id": "external_usb_zone", "inside": True,
          "position": [0.4, 0.6]}],
        armed=True, now=109.0,
    )
    detector._decision_tracks = dict(result.tracks)


def test_short_same_process_camera_reconnect_preserves_state(monkeypatch):
    import ai.person_detector as pd

    clock = {"now": 110.0}
    monkeypatch.setattr(pd.time, "monotonic", lambda: clock["now"])
    detector = CameraDetector(model=object())
    _prime_active_track(detector)

    detector._set_camera_health(False, "temporary camera outage")
    clock["now"] = 112.0
    detector._set_camera_health(True)

    assert 41 in detector._track_state
    assert 41 not in detector._authorized_tracks  # visual outage always revokes RFID identity
    session_id = detector._decision_tracks["41"]["session_id"]
    assert session_id is not None
    handover = detector._decision_engine.evaluate(
        [{"track_id": 42, "zone_id": "external_usb_zone", "inside": True,
          "position": [0.405, 0.6]}],
        armed=True, now=112.1,
    )
    assert handover.tracks["42"]["session_id"] == session_id
    assert detector._track_state_preservation_last == "preserved_short_reconnect"
    recovered = next(e for e in detector.get_events() if e["type"] == "camera_recovered")
    assert recovered["track_state_policy"] == "preserved_short_reconnect"
    assert recovered["outage_seconds"] == 2.0


def test_long_camera_outage_resets_track_authorization_and_decision_state(monkeypatch):
    import ai.person_detector as pd

    clock = {"now": 110.0}
    monkeypatch.setattr(pd.time, "monotonic", lambda: clock["now"])
    detector = CameraDetector(model=object())
    _prime_active_track(detector)

    detector._set_camera_health(False, "long camera outage")
    clock["now"] = 114.0
    detector._set_camera_health(True)

    assert detector._track_state == {}
    assert detector._authorized_tracks == {}
    assert detector._rfid_tickets == {}
    assert detector._decision_tracks == {}
    assert detector._decision_engine.alarm_state == "SAFE"
    assert detector._track_state_preservation_last == "reset_after_long_outage"


def test_status_explains_tracking_preservation_scope():
    detector = CameraDetector(model=object())
    policy = detector.status()["track_state_preservation"]
    assert policy["enabled"] is True
    assert policy["window_seconds"] <= 3.5
    assert policy["scope"] == "same_process_camera_reconnect_only"
