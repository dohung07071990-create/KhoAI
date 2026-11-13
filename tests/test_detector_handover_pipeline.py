"""Detector-to-engine regression: ID swaps during inside hysteresis retain the session."""
import numpy as np

from ai import person_detector as pd


def test_process_frame_id_swap_on_raw_inside_first_frame_keeps_alarm_clock(monkeypatch, tmp_path):
    # Drive the real detector adapter and _process_frame with deterministic time
    # and synthetic detector outputs; no camera, YOLO weights, or wall clock needed.
    clock = {"now": 0.0}
    monkeypatch.setattr(pd.time, "monotonic", lambda: clock["now"])
    monkeypatch.setattr(pd, "current_zone_period", lambda *args, **kwargs: "day")
    monkeypatch.setattr(pd, "ENTER_CONFIRM_SECONDS", 0.10)
    monkeypatch.setattr(pd, "EXIT_CONFIRM_SECONDS", 0.10)
    monkeypatch.setattr(pd, "ENTRY_GRACE_SECONDS", 8.0)
    monkeypatch.setattr(pd, "TRACK_HOLD_SECONDS", 5.0)
    monkeypatch.setattr(pd, "HANDOVER_MAX_GAP_SECONDS", 3.5)
    monkeypatch.setattr(pd, "HANDOVER_MATCH_RADIUS", 0.08)
    monkeypatch.setattr(pd, "HANDOVER_EXCLUSION_RADIUS", 0.02)
    monkeypatch.setattr(pd, "EVIDENCE_DIR", tmp_path / "evidence")

    detector = pd.CameraDetector(camera_index=0, model=object())
    detector.zone = pd.DEFAULT_ZONE
    detector._zone_check_at = 10_000.0  # disable filesystem reload in this unit test
    detector._heatmap_last_tick = 0.0
    detector.anti_theft_enabled = True

    current = {"id": 1}
    def fake_detect(_frame):
        if current["id"] is None:
            return []
        return [{"id": current["id"], "box": (250.0, 150.0, 400.0, 400.0), "conf": 0.99}]
    monkeypatch.setattr(detector, "_detect", fake_detect)

    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    snapshots = []
    # Each identity is observed for 3.5 s; the 0.5 s gap is within the 3.5 s
    # engine handover window. First frame of each replacement ID is raw_inside=True
    # while confirmed inside remains False for the entry hysteresis interval.
    schedule = []
    for base, tid in ((0.0, 1), (4.0, 2), (8.0, 3), (12.0, 4)):
        for step in range(36):
            schedule.append((base + step * 0.1, tid))
        for step in range(1, 5):
            schedule.append((base + 3.5 + step * 0.1, None))

    for stamp, tid in schedule:
        clock["now"] = stamp
        current["id"] = tid
        detector._process_frame(frame.copy())
        if tid is not None:
            snapshots.append((stamp, detector.alarm_state,
                              detector._decision_tracks.get(str(tid), {}).get("session_id")))

    alarm_times = [stamp for stamp, state, _session in snapshots if state == "ALARM"]
    assert alarm_times, "ID swaps reset the intrusion timer; ALARM was never reached"
    assert min(alarm_times) <= 12.0
    session_ids = {session for _stamp, _state, session in snapshots if session}
    assert len(session_ids) == 1, session_ids
