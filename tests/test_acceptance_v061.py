"""Acceptance regression tests from the v0.6.1 tester report."""
import os
import pytest

from ai.decision import DecisionConfig, DecisionEngine


def obs(track_id, inside=True, zones=(), dwell=0):
    return {"track_id": track_id, "zone_id": "zone_a", "inside": inside,
            "authorized_zones": list(zones), "dwell_seconds": dwell}


def test_A1_authorized_worker_does_not_reset_intruder_cumulative_clock():
    engine = DecisionEngine(DecisionConfig(entry_grace_seconds=15, presence_release_seconds=30))
    worker = obs(1, True, ["zone_a"])
    stranger = obs(2)
    engine.evaluate([worker, stranger], armed=True, now=0)
    now = 0.0
    # First visit: 10 seconds present.
    for tick in range(1, 101):
        now = tick / 10
        engine.evaluate([worker, stranger], armed=True, now=now)
    # Short exit: 0.5 seconds. This pauses, but does not reset, the clock.
    for tick in range(1, 6):
        now = 10 + tick / 10
        engine.evaluate([worker], armed=True, now=now)
    # Second visit: ALARM at 15 cumulative occupied seconds.
    for tick in range(1, 61):
        now = 10.5 + tick / 10
        result = engine.evaluate([worker, stranger], armed=True, now=now)
        if result.alarm_state == "ALARM":
            break
    assert result.alarm_state == "ALARM"
    assert 15.5 <= now <= 16.5


def test_A2_one_missed_frame_does_not_reset_intruder_grace():
    engine = DecisionEngine(DecisionConfig(entry_grace_seconds=15))
    stranger = obs(2)
    engine.evaluate([stranger], armed=True, now=0.0)
    result = None
    # 20 fps for 15 seconds, omit exactly the frame at 7.0 seconds.
    for tick in range(1, 311):
        now = tick / 20
        if tick == 140:
            result = engine.evaluate([], armed=True, now=now)
        else:
            result = engine.evaluate([stranger], armed=True, now=now)
        if result.alarm_state == "ALARM":
            break
    assert result is not None and result.alarm_state == "ALARM"
    assert 15.0 <= now <= 15.5


def test_A3_authorizing_P_does_not_reset_Q_clock():
    engine = DecisionEngine(DecisionConfig(entry_grace_seconds=15))
    p, q = obs(1), obs(2)
    engine.evaluate([p, q], armed=True, now=0)
    result = engine.evaluate([obs(1, True, ["zone_a"]), q], armed=True, now=10)
    assert result.tracks["2"]["state"] == "WARNING"
    result = engine.evaluate([obs(1, True, ["zone_a"]), q], armed=True, now=15)
    assert result.tracks["2"]["state"] == "ALARM"


def test_A4_authorizing_only_stranger_resets_clock_for_next_person():
    engine = DecisionEngine(DecisionConfig(entry_grace_seconds=15))
    first = obs(1)
    engine.evaluate([first], armed=True, now=0)
    engine.evaluate([first], armed=True, now=10)
    authorized = obs(1, True, ["zone_a"])
    engine.evaluate([authorized], armed=True, now=10.5)
    second = obs(2)
    result = engine.evaluate([authorized, second], armed=True, now=11)
    assert result.tracks["2"]["state"] == "WARNING"
    result = engine.evaluate([authorized, second], armed=True, now=25.9)
    assert result.tracks["2"]["state"] == "WARNING"
    result = engine.evaluate([authorized, second], armed=True, now=26)
    assert result.tracks["2"]["state"] == "ALARM"


def test_A5_zone_clock_resets_after_31_seconds_empty():
    engine = DecisionEngine(DecisionConfig(entry_grace_seconds=15, presence_release_seconds=30))
    stranger = obs(1)
    engine.evaluate([stranger], armed=True, now=0)
    engine.evaluate([stranger], armed=True, now=10)
    engine.evaluate([], armed=True, now=10.1)
    engine.evaluate([], armed=True, now=41.1)
    result = engine.evaluate([stranger], armed=True, now=41.2)
    assert result.tracks["1"]["state"] == "WARNING"


def test_B1_review_is_not_aggregate_warning_or_alarm():
    engine = DecisionEngine(DecisionConfig(dwell_review_seconds=300))
    worker = obs(7, True, ["zone_a"])
    for t in (0, 60, 120, 240, 299):
        result = engine.evaluate([worker], armed=True, now=t)
        assert result.tracks["7"]["state"] == "AUTHORIZED"
    result = engine.evaluate([obs(7, True, ["zone_a"], dwell=300)], armed=True, now=300)
    assert result.tracks["7"]["state"] == "REVIEW"
    assert result.alarm_state == "SAFE"


def test_B2_authorization_max_expiry_emits_explicit_event(monkeypatch):
    import ai.person_detector as pd
    detector = pd.CameraDetector(model=object())
    monkeypatch.setattr(pd, "AUTH_MAX_SECONDS", 5.0)
    detector._authorized_tracks[8] = {
        "uid": "TEST", "at": 100.0, "allowed_zones": ["external_usb_zone"]
    }
    detector._apply_events([], [], 105.0)
    assert 8 not in detector._authorized_tracks
    event = next(e for e in detector.get_events() if e["type"] == "authorization_expired")
    assert event["reason"] == "auth_max_seconds"
    engine = DecisionEngine(DecisionConfig(entry_grace_seconds=15))
    result = engine.evaluate([obs(8)], armed=True, now=105.0)
    assert result.tracks["8"]["state"] == "WARNING"
    result = engine.evaluate([obs(8)], armed=True, now=120.0)
    assert result.tracks["8"]["state"] == "ALARM"


def test_B3_authorization_is_not_handed_over_after_occlusion_new_id():
    from ai.person_detector import CameraDetector
    detector = CameraDetector(camera_index=0, model=object())
    detector._authorized_tracks[8] = {"uid": "AABBCCDD", "name": "Staff", "at": 1.0,
                                      "allowed_zones": ["external_usb_zone"]}
    detector._track_state[8] = {"inside": True, "last_seen_at": 10.0,
                                "last_box": (100.0, 100.0, 200.0, 300.0)}
    detections = [{"id": 9, "box": (105.0, 102.0, 205.0, 302.0), "raw_inside": True}]
    detector._update_tracks(detections, 12.0)
    assert 8 not in detector._authorized_tracks
    assert 9 not in detector._authorized_tracks
    assert any(event["type"] == "authorization_revoked" and event.get("reason") == "track_lost"
               for event in detector.get_events())
    assert not any(event["type"] == "authorization_handover" for event in detector.get_events())


def test_C1_anonymous_half_second_does_not_lower_existing_alarm():
    engine = DecisionEngine(DecisionConfig(entry_grace_seconds=0, anonymous_debounce_seconds=1))
    stranger = obs(10)
    assert engine.evaluate([stranger], armed=True, now=0).alarm_state == "ALARM"
    result = engine.evaluate([stranger], armed=True, now=0.25, anonymous_inside=True)
    assert result.alarm_state == "ALARM"
    result = engine.evaluate([stranger], armed=True, now=0.5, anonymous_inside=False)
    assert result.alarm_state == "ALARM"
    assert not any(e["type"] == "alarm_state_changed" for e in result.events)


def test_C2_anonymous_half_second_alone_does_not_alarm_or_emit_event():
    engine = DecisionEngine(DecisionConfig(anonymous_debounce_seconds=1))
    engine.evaluate([], armed=True, now=0, anonymous_inside=True)
    result = engine.evaluate([], armed=True, now=0.5, anonymous_inside=False)
    assert result.alarm_state == "SAFE"
    assert not result.events


def test_C3_anonymous_alarm_is_max_of_track_warning_and_returns_after_hold():
    engine = DecisionEngine(DecisionConfig(entry_grace_seconds=15, anonymous_debounce_seconds=1,
                                            track_hold_seconds=5))
    warning = obs(11)
    engine.evaluate([warning], armed=True, now=0)
    engine.evaluate([warning], armed=True, now=5, anonymous_inside=True)
    result = engine.evaluate([warning], armed=True, now=6.1, anonymous_inside=True)
    assert result.alarm_state == "ALARM"
    result = engine.evaluate([warning], armed=True, now=6.2, anonymous_inside=False)
    assert result.alarm_state == "ALARM"
    result = engine.evaluate([warning], armed=True, now=11.3, anonymous_inside=False)
    assert result.alarm_state == "WARNING"


def test_D1_evidence_images_are_rate_limited_but_events_are_kept(tmp_path, monkeypatch):
    import ai.person_detector as pd
    detector = pd.CameraDetector(model=object())
    monkeypatch.setattr(pd, "EVIDENCE_DIR", tmp_path)
    monkeypatch.setattr(pd, "EVIDENCE_INTERVAL_SECONDS", 1.0)
    clock = {"now": 0.0}
    monkeypatch.setattr(pd.time, "monotonic", lambda: clock["now"])
    for i in range(10):
        before = {str(e["event_id"]) for e in detector.get_events()}
        detector._emit("synthetic", i, "synthetic event", severity="warning")
        detector._attach_evidence(b"jpeg", before)
        clock["now"] += 0.2
    assert len(detector.get_events()) == 10
    assert len(list(tmp_path.glob("*.jpg"))) <= 2


def test_E1_authorized_track_near_zone_remains_safe_without_warning_events():
    engine = DecisionEngine(DecisionConfig(entry_grace_seconds=15))
    # First frame is in the expanded warning polygon but not yet confirmed inside.
    result = engine.evaluate([obs(21, inside=False, zones=("zone_a",)) | {"warning": True}],
                             armed=True, now=0.0)
    assert result.tracks["21"]["state"] == "SAFE"
    assert not any(event["type"] == "zone_warning" for event in result.events)
    # Confirmation into the protected polygon must not create WARNING either.
    result = engine.evaluate([obs(21, inside=True, zones=("zone_a",))], armed=True, now=0.1)
    assert result.tracks["21"]["state"] == "AUTHORIZED"
    assert result.alarm_state == "SAFE"
    assert not any(event["type"] in {"zone_warning", "alarm_state_changed"} for event in result.events)


def test_unauthorized_track_near_zone_still_gets_warning():
    engine = DecisionEngine(DecisionConfig(entry_grace_seconds=15))
    result = engine.evaluate([obs(22, inside=False) | {"warning": True}], armed=True, now=0.0)
    assert result.tracks["22"]["state"] == "PASSERBY"
    confirmed = engine.evaluate([obs(22, inside=False) | {"warning": True}], armed=True, now=3.0)
    assert confirmed.tracks["22"]["state"] == "WARNING"
    assert any(event["type"] == "zone_warning" for event in confirmed.events)


def test_D1a_all_events_from_same_frame_share_one_evidence_file(tmp_path, monkeypatch):
    import ai.person_detector as pd
    detector = pd.CameraDetector(model=object())
    monkeypatch.setattr(pd, "EVIDENCE_DIR", tmp_path)
    monkeypatch.setattr(pd, "EVIDENCE_INTERVAL_SECONDS", 0.0)
    before = {str(event["event_id"]) for event in detector.get_events()}
    detector._emit("alarm_state_changed", -1, "ALARM", severity="critical")
    detector._emit("unauthorized_entry", 7, "Unauthorized", severity="critical")
    detector._emit("zone_entry", 7, "Entry", severity="info")
    detector._attach_evidence(b"same-frame-jpeg", before)
    new_events = [event for event in detector.get_events() if event["event_id"] not in before]
    urls = {event["evidence_url"] for event in new_events}
    assert len(new_events) == 3
    assert len(urls) == 1 and None not in urls
    assert len({event["evidence_filename"] for event in new_events}) == 1
    assert all(event["evidence_status"] == "available" for event in new_events)
    assert len(list(tmp_path.glob("*.jpg"))) == 1
    assert next(tmp_path.glob("*.jpg")).read_bytes() == b"same-frame-jpeg"


def test_rfid_ticket_auto_binds_only_swipe_time_single_candidate_when_explicitly_enabled(monkeypatch):
    from ai import person_detector as pd
    clock = {"now": 10.0}
    monkeypatch.setattr(pd.time, "monotonic", lambda: clock["now"])
    monkeypatch.setattr(pd, "RFID_AUTO_BIND_ENABLED", True)
    detector = pd.CameraDetector(camera_index=0, model=object())
    detector.rfid_entry_roi = ((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0))
    detector._last_frame_size = (640, 480)
    detector._last_raw_at = 10.0
    detector._camera_frame_times.extend([9.0, 9.5, 10.0])
    detector._last_detection_at = 10.0
    detector._last_detections = [{"id": 21, "box": (100, 100, 200, 300)}]
    detector._track_state[21] = {"inside": False, "last_seen_at": 10.0, "last_box": (100, 100, 200, 300)}
    detector.create_rfid_ticket("AABBCCDD", "Worker", ["external_usb_zone"], ttl_seconds=20)
    detections = [{"id": 21, "box": (100, 100, 200, 300)}]
    detector._try_bind_rfid_tickets(detections, 10.0, (640, 480))
    assert 21 not in detector._authorized_tracks
    clock["now"] = 10.31
    detector._try_bind_rfid_tickets(detections, 10.31, (640, 480))
    assert detector._authorized_tracks[21]["uid"] == "AABBCCDD"
    assert not detector.has_rfid_ticket("AABBCCDD")
    assert any(event["type"] == "rfid_ticket_bound" for event in detector.get_events())


def test_zone_hysteresis_uses_seconds_not_frame_counts(monkeypatch):
    from ai import person_detector as pd
    detector = pd.CameraDetector(camera_index=0, model=object())
    monkeypatch.setattr(pd, "ENTER_CONFIRM_SECONDS", 0.2)
    inside = {"id": 4, "box": (100, 100, 200, 300), "raw_inside": True}
    d1 = dict(inside); detector._update_tracks([d1], 1.0)
    assert d1["inside"] is False
    d2 = dict(inside); detector._update_tracks([d2], 1.1)
    assert d2["inside"] is False
    d3 = dict(inside); detector._update_tracks([d3], 1.21)
    assert d3["inside"] is True


def test_rate_limited_event_reuses_last_evidence_url(tmp_path, monkeypatch):
    from ai import person_detector as pd
    detector = pd.CameraDetector(camera_index=0, model=object())
    monkeypatch.setattr(pd, "EVIDENCE_DIR", tmp_path)
    monkeypatch.setattr(pd, "EVIDENCE_INTERVAL_SECONDS", 10.0)
    detector._last_evidence_url = "/api/camera/evidence/" + "a" * 32 + ".jpg"
    detector._last_evidence_at = __import__("time").monotonic()
    detector._last_evidence_timestamp = "2026-11-05T12:00:00+07:00"
    detector._evidence_last_saved_at = detector._last_evidence_at
    before = {event["event_id"] for event in detector.get_events()}
    detector._emit("zone_exit", 3, "exit", severity="low")
    detector._attach_evidence(b"jpeg", before)
    event = detector.get_events()[0]
    assert event["evidence_url"] == detector._last_evidence_url
    assert event["evidence_reused"] is True
    assert event["image_age_ms"] >= 0


def test_rfid_ticket_does_not_bind_when_two_people_are_in_entry_roi(monkeypatch):
    from ai import person_detector as pd
    detector = pd.CameraDetector(camera_index=0, model=object())
    detector.rfid_entry_roi = ((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0))
    now = __import__("time").monotonic()
    detector._last_raw_at = now
    detector._camera_frame_times.extend([now - 1.0, now - 0.5, now])
    detector.create_rfid_ticket("11223344", "Worker", ["external_usb_zone"], ttl_seconds=20)
    detections = [{"id": 1, "box": (10, 10, 100, 200)}, {"id": 2, "box": (110, 10, 200, 200)}]
    detector._try_bind_rfid_tickets(detections, 10.0, (640, 480))
    assert not detector._authorized_tracks
    assert detector.has_rfid_ticket("11223344")


@pytest.mark.parametrize("edge,boxes", [
    ("left", [(20, 100, 100, 300), (10, 100, 90, 300), (0, 100, 80, 300)]),
    ("right", [(540, 100, 620, 300), (550, 100, 630, 300), (560, 100, 640, 300)]),
    ("top", [(100, 20, 180, 220), (100, 10, 180, 210), (100, 0, 180, 200)]),
    ("bottom", [(100, 180, 180, 460), (100, 190, 180, 470), (100, 200, 180, 480)]),
])
def test_frame_edge_outward_motion_detected_for_each_boundary(monkeypatch, edge, boxes):
    from ai import person_detector as pd
    detector = pd.CameraDetector(camera_index=0, model=object())
    det = {"id": 31, "box": boxes[0]}
    assert not detector._is_outward_frame_exit(det, 0.0, 640, 480)
    det["box"] = boxes[1]
    detector._is_outward_frame_exit(det, 0.05, 640, 480)
    det["box"] = boxes[2]
    assert detector._is_outward_frame_exit(det, 0.10, 640, 480), edge


def test_frame_edge_tangential_motion_is_not_outward(monkeypatch):
    from ai import person_detector as pd
    detector = pd.CameraDetector(camera_index=0, model=object())
    det = {"id": 32, "box": (2, 100, 82, 300)}
    assert not detector._is_outward_frame_exit(det, 0.0, 640, 480)
    det["box"] = (2, 110, 82, 310)
    detector._is_outward_frame_exit(det, 0.05, 640, 480)
    det["box"] = (2, 120, 82, 320)
    assert not detector._is_outward_frame_exit(det, 0.10, 640, 480)


def test_frame_edge_stationary_and_insufficient_history_allow_handover(monkeypatch):
    from ai import person_detector as pd
    detector = pd.CameraDetector(camera_index=0, model=object())
    det = {"id": 33, "box": (2, 100, 82, 300)}
    assert not detector._is_outward_frame_exit(det, 0.0, 640, 480)
    assert not detector._is_outward_frame_exit(det, 0.05, 640, 480)
    assert not detector._is_outward_frame_exit(det, 0.10, 640, 480)
    # A fresh ID with too few samples is intentionally not classified as an exit.
    fresh = {"id": 34, "box": (2, 100, 82, 300)}
    assert not detector._is_outward_frame_exit(fresh, 1.0, 640, 480)



@pytest.mark.parametrize("fps", [5, 10, 25])
@pytest.mark.parametrize("noise_px", [2, 3, 5])
def test_stationary_person_at_bottom_edge_is_not_classified_as_exiting_under_box_jitter(
        fps, noise_px):
    """Deterministic periodic bbox jitter should not look like sustained outward motion."""
    import math
    from ai import person_detector as pd

    detector = pd.CameraDetector(camera_index=0, model=object())
    step = 1.0 / fps
    classified = []
    for index in range(fps * 3):
        # Fixed mean footpoint near the lower edge, with bounded detector jitter.
        jitter = noise_px * math.sin(index * 2.399963229728653)
        foot_y = 477.0 + jitter
        det = {"id": 700 + fps + noise_px, "box": (200.0, foot_y - 180.0, 280.0, foot_y)}
        classified.append(detector._is_outward_frame_exit(det, index * step, 640, 480))
    assert not any(classified), (fps, noise_px, classified)

def test_rfid_authorization_is_removed_after_track_is_lost_over_five_seconds(monkeypatch):
    from ai import person_detector as pd
    detector = pd.CameraDetector(camera_index=0, model=object())
    monkeypatch.setattr(pd, "TRACK_HOLD_SECONDS", 5.0)
    detector._authorized_tracks[55] = {"uid": "AABBCCDD", "name": "Worker", "at": 0.0,
                                       "allowed_zones": ["external_usb_zone"]}
    first = {"id": 55, "box": (100, 100, 180, 300), "raw_inside": False,
             "exit_boundary_inside": False}
    detector._update_tracks([first], 0.0)
    detector._update_tracks([], 5.1)
    assert 55 not in detector._authorized_tracks



def test_rfid_entry_roi_is_persisted_and_used_by_detector(tmp_path, monkeypatch):
    from ai import person_detector as pd
    detector = pd.CameraDetector(camera_index=0, model=object())
    monkeypatch.setattr(pd, "RFID_ENTRY_ROI_FILE", tmp_path / "entry_roi.json")
    points = ((0.1, 0.2), (0.9, 0.2), (0.9, 0.8), (0.1, 0.8))
    saved = detector.set_rfid_entry_roi(points)
    assert saved == points
    assert (tmp_path / "entry_roi.json").is_file()
    assert detector.rfid_entry_roi == points


def test_multiple_rfid_tickets_never_auto_bind_even_with_one_person():
    from ai import person_detector as pd
    detector = pd.CameraDetector(camera_index=0, model=object())
    detector.rfid_entry_roi = ((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0))
    now = __import__("time").monotonic()
    detector._last_raw_at = now
    detector._camera_frame_times.extend([now - 1.0, now - 0.5, now])
    detector.create_rfid_ticket("11112222", "A", ["external_usb_zone"], ttl_seconds=20)
    detector.create_rfid_ticket("33334444", "B", ["external_usb_zone"], ttl_seconds=20)
    detector._try_bind_rfid_tickets([{"id": 1, "box": (100, 100, 200, 300)}], 10.0, (640, 480))
    assert not detector._authorized_tracks
    assert len(detector.pending_rfid_tickets()) == 2


@pytest.mark.parametrize("fps", [8, 15, 25])
@pytest.mark.parametrize("speed_ratio", [0.05, 0.10, 0.20, 0.35, 0.50])
def test_frame_edge_outward_detection_is_stable_across_fps(monkeypatch, fps, speed_ratio):
    from ai import person_detector as pd
    detector = pd.CameraDetector(camera_index=0, model=object())
    margin = 640 * pd.HANDOVER_EDGE_MARGIN_RATIO
    step = 1.0 / fps
    start_x = margin + speed_ratio * 640 * step * 2
    det = {"id": 88, "box": (start_x, 100, start_x + 80, 300)}
    detector._is_outward_frame_exit(det, 0.0, 640, 480)
    det["box"] = (start_x - speed_ratio * 640 * step, 100,
                  start_x + 80 - speed_ratio * 640 * step, 300)
    detector._is_outward_frame_exit(det, step, 640, 480)
    det["box"] = (margin, 100, margin + 80, 300)
    assert detector._is_outward_frame_exit(det, 2 * step, 640, 480)


def test_rfid_entry_roi_rejects_self_intersection_and_zero_area(tmp_path, monkeypatch):
    from ai import person_detector as pd
    detector = pd.CameraDetector(camera_index=0, model=object())
    monkeypatch.setattr(pd, "RFID_ENTRY_ROI_FILE", tmp_path / "entry_roi.json")
    with pytest.raises(ValueError, match="diện tích bằng 0|tự cắt"):
        detector.set_rfid_entry_roi(((0.1, 0.1), (0.9, 0.9), (0.1, 0.9), (0.9, 0.1)))
    # Self-crossing five-point polygon with non-zero signed area.
    with pytest.raises(ValueError, match="tự cắt"):
        detector.set_rfid_entry_roi(((0.5, 0.05), (0.9, 0.9), (0.05, 0.35),
                                     (0.95, 0.35), (0.1, 0.9)))
    assert not (tmp_path / "entry_roi.json").exists()


def test_clipped_left_edge_still_detects_body_motion_outward():
    from ai import person_detector as pd
    detector = pd.CameraDetector(camera_index=0, model=object())
    det = {"id": 91, "box": (18, 100, 98, 300)}
    detector._is_outward_frame_exit(det, 0.0, 640, 480)
    det["box"] = (0, 100, 80, 300)
    detector._is_outward_frame_exit(det, 0.1, 640, 480)
    det["box"] = (0, 100, 60, 300)
    assert detector._is_outward_frame_exit(det, 0.2, 640, 480)


@pytest.mark.parametrize("edge", ["left", "right", "top", "bottom"])
@pytest.mark.parametrize("fps", [8, 15, 25])
@pytest.mark.parametrize("speed_ratio", [0.05, 0.10])
def test_slow_partially_clipped_exit_detected_until_track_is_lost(edge, fps, speed_ratio):
    from ai import person_detector as pd
    detector = pd.CameraDetector(camera_index=0, model=object())
    width, height, box_w, box_h = 640, 480, 80.0, 200.0
    step = 1.0 / fps
    velocity = speed_ratio * (width if edge in {"left", "right"} else height)
    detected_at_last_observation = False
    for frame_index in range(int(12.0 * fps)):
        shift = velocity * frame_index * step
        if edge == "left":
            x1, x2 = 35.0 - shift, 35.0 - shift + box_w
            box = (max(0.0, x1), 120.0, max(0.0, min(float(width), x2)), 320.0)
            visible = box[2] > 20.0
        elif edge == "right":
            x1, x2 = width - 100.0 + shift, width - 100.0 + shift + box_w
            box = (min(float(width), max(0.0, x1)), 120.0, min(float(width), x2), 320.0)
            visible = width - box[0] > 20.0
        elif edge == "top":
            y1, y2 = 35.0 - shift, 35.0 - shift + box_h
            box = (200.0, max(0.0, y1), 280.0, max(0.0, min(float(height), y2)))
            visible = box[3] > 20.0
        else:
            y1, y2 = height - 100.0 + shift, height - 100.0 + shift + box_h
            box = (200.0, min(float(height), max(0.0, y1)), 280.0, min(float(height), y2))
            visible = height - box[1] > 20.0
        if not visible:
            break
        det = {"id": 1000 + (hash((edge, fps, speed_ratio)) % 10000), "box": box}
        detected_at_last_observation = detector._is_outward_frame_exit(
            det, frame_index * step, width, height
        )
    assert detected_at_last_observation, (edge, fps, speed_ratio)
