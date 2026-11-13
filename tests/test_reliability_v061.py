from ai.decision import DecisionConfig, DecisionEngine
from ai.person_detector import CameraDetector


def test_card_authorization_survives_zone_exit_but_not_unconfirmed_track_gap():
    detector = CameraDetector(model=object())
    detector._authorized_tracks[7] = {"uid": "A1", "at": 0.0, "allowed_zones": ["external_usb_zone"]}
    detector._inside_since[7] = 0.0
    detector._apply_events([], [7], 1.0)
    assert 7 in detector._authorized_tracks
    detector._track_state[7] = {"in": 0, "out": 0, "inside": True, "missing": 0, "last_seen_at": 1.0}
    detector._update_tracks([], 1.5)
    assert 7 in detector._authorized_tracks  # 0.5s missing is within short tolerance
    detector._update_tracks([], 2.0)
    assert 7 not in detector._authorized_tracks  # >0.75s missing fails closed


def test_status_contract_has_health_and_temporary_incident_fields():
    detector = CameraDetector(model=object())
    status = detector.status()
    assert "camera_ok" in status and "ai_ok" in status
    assert "tracking_enabled" in status
    assert "review_person_ids" in status
    assert status["latched"] is False and status["acknowledged"] is False
    assert status["siren"] is False and status["incidents"] == []


def test_health_watchdog_escalates_camera_failure_after_configured_window(monkeypatch):
    import ai.person_detector as pd

    detector = CameraDetector(model=object())
    detector.anti_theft_enabled = True
    detector._started_at = 0.0
    detector._last_raw_at = 90.0
    detector._last_processed_at = 99.0
    fake_now = {"value": 100.0}
    monkeypatch.setattr(pd.time, "monotonic", lambda: fake_now["value"])

    class OneTick:
        def __init__(self): self.calls = 0
        def wait(self, _seconds):
            self.calls += 1
            return self.calls > 1

    detector._stop = OneTick()
    detector._health_watchdog_loop()
    assert detector.alarm_state == "WARNING"
    fake_now["value"] = 130.0
    detector._stop = OneTick()
    detector._health_watchdog_loop()
    assert detector.alarm_state == "ALARM"


def test_health_watchdog_detects_model_failure_separately(monkeypatch):
    import ai.person_detector as pd

    detector = CameraDetector(model=None)
    detector.anti_theft_enabled = True
    detector._started_at = 0.0
    detector._last_raw_at = 99.0
    detector._camera_frame_times.extend([98.0, 98.5, 99.0])
    detector._camera_health = True
    detector._last_processed_at = 99.0
    monkeypatch.setattr(pd.time, "monotonic", lambda: 100.0)

    class OneTick:
        def __init__(self): self.calls = 0
        def wait(self, _seconds):
            self.calls += 1
            return self.calls > 1

    detector._stop = OneTick()
    detector._health_watchdog_loop()
    assert detector._health_reason == "ai_model_unavailable"
    assert detector.alarm_state == "WARNING"


def test_arming_with_camera_already_offline_starts_warning_immediately(monkeypatch):
    import ai.person_detector as pd

    detector = CameraDetector(model=object())
    detector.anti_theft_enabled = False
    detector._started_at = 0.0
    detector._last_raw_at = float("-inf")
    detector._last_processed_at = float("-inf")
    monkeypatch.setattr(pd.time, "monotonic", lambda: 100.0)
    result = detector.set_anti_theft(True)
    assert result["alarm_state"] == "WARNING"


def test_camera_offline_during_startup_grace_is_reported_only_after_grace(monkeypatch):
    import ai.person_detector as pd
    detector = CameraDetector(model=object())
    detector._started_at = 100.0
    detector._last_raw_at = float("-inf")
    detector._last_processed_at = float("-inf")
    fake_now = {"value": 110.0}
    monkeypatch.setattr(pd.time, "monotonic", lambda: fake_now["value"])
    detector._set_camera_health(False, "startup outage")
    assert not any(event["type"] == "camera_offline" for event in detector.get_events())

    class OneTick:
        def __init__(self): self.calls = 0
        def wait(self, _seconds):
            self.calls += 1
            return self.calls > 1

    fake_now["value"] = 161.0
    detector._stop = OneTick()
    detector._health_watchdog_loop()
    events = [event["type"] for event in detector.get_events()]
    assert events.count("camera_offline") == 1
    assert detector.alarm_state == "WARNING"
