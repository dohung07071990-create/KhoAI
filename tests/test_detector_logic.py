"""Pytest integration test with a generated video and fake YOLO model; no physical camera required."""
import os, sys, tempfile, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
tmp = tempfile.mkdtemp()

import cv2, numpy as np
from ai import person_detector as pd
from ai.camera_utils import parse_camera_source, open_camera, list_cameras
from ai.envfile import _parse_line


def test_detector_logic(monkeypatch):
    # Isolate configuration at module level; do not mutate process-wide environment
    # during test collection (other modules may have imported person_detector already).
    monkeypatch.setattr(pd, "ZONE_FILE", Path(tmp) / "zone.json")
    monkeypatch.setattr(pd, "EVIDENCE_DIR", Path(tmp) / "evidence")
    monkeypatch.setattr(pd, "ENTER_CONFIRM_SECONDS", 0.05)
    monkeypatch.setattr(pd, "EXIT_CONFIRM_SECONDS", 0.08)
    monkeypatch.setattr(pd, "ENTRY_GRACE_SECONDS", 0.0)
    # This integration test reads a synthetic video file faster than real time;
    # keep its camera-stability window short while dedicated recovery tests cover 1s.
    monkeypatch.setattr(pd, "CAMERA_RECOVERY_STABLE_SECONDS", 0.05)
    W, H = 640, 480
    poly = pd.zone_to_pixels(pd.DEFAULT_ZONE, W, H)

    # 0. Lịch vùng và vùng WARNING mở rộng
    assert pd.scale_zone(pd.DEFAULT_ZONE, 1.1) != pd.DEFAULT_ZONE
    from datetime import datetime
    assert pd.current_zone_period(datetime(2026, 11, 3, 17, 59, tzinfo=pd.BUSINESS_TZ)) == "day"
    assert pd.current_zone_period(datetime(2026, 11, 3, 18, 0, tzinfo=pd.BUSINESS_TZ)) == "night"
    print("0. lịch vùng OK")

    # 1. Luật vùng
    assert pd.is_box_in_zone((250, 150, 400, 400), (W, H), poly)            # chân trong vùng
    assert not pd.is_box_in_zone((250, 20, 400, 150), (W, H), poly)         # chân ở trên vùng (ngoài)
    assert not pd.is_box_in_zone((0, 150, 20, 300), (W, H), poly)           # sát mép trái, ngoài
    assert pd.is_box_in_zone((200, 150, 440, 479), (W, H), poly)            # chân bị cắt đáy khung -> vẫn trong (lỗi cũ: False)
    assert not pd.is_box_in_zone((200, 150, 440, 479), (W, H), poly, truncated_fallback=False)  # đúng hành vi cũ
    mask = np.zeros((H, W), np.uint8); cv2.fillPoly(mask, [np.round(poly).astype(np.int32).reshape(-1,1,2)], 255)
    assert pd.is_box_in_zone((250, 150, 400, 400), (W, H), poly, "overlap", mask, 0.3)
    assert not pd.is_box_in_zone((250, 20, 400, 120), (W, H), poly, "overlap", mask, 0.3)
    # Signed-distance exit buffer: points just outside remain inside the spatial hysteresis band.
    margin_px = 0.02 * min(W, H)
    assert cv2.pointPolygonTest(poly.astype(np.int32), (300, 188), True) >= -margin_px
    assert cv2.pointPolygonTest(poly.astype(np.int32), (300, 170), True) < -margin_px
    print("1. luật vùng + spatial exit buffer OK")

    # 2. Parse cấu hình
    assert parse_camera_source("1") == 1 and parse_camera_source("") == "auto" and parse_camera_source("rtsp://x") == "rtsp://x"
    assert _parse_line('CAMERA_INDEX=1  # usb') == ("CAMERA_INDEX", "1")
    assert _parse_line('X="a b"') == ("X", "a b") and _parse_line("# c") is None
    try: pd.validate_zone([(0.1, 0.1), (0.2, 0.2), (0.3, 0.3)]); raise SystemExit("phải lỗi")
    except ValueError: pass
    print("2. parse OK")

    # 3. Không có camera -> None, không treo
    assert open_camera(9, fallback_scan=False, warmup_frames=2) is None
    print("3. không camera OK")

    # 4. Pipeline đầy đủ với video giả + model giả
    vid = os.path.join(tmp, "fake.avi")
    vw = cv2.VideoWriter(vid, cv2.VideoWriter_fourcc(*"MJPG"), 30, (W, H))
    for i in range(900):
        f = np.full((H, W, 3), 60, np.uint8); cv2.putText(f, str(i), (10, 60), 0, 1, (255,255,255), 2); vw.write(f)
    vw.release()

    class T:  # giả torch tensor
        def __init__(s, a): s.a = np.asarray(a)
        def cpu(s): return s
        def numpy(s): return s.a
        def int(s): return s
        def tolist(s): return s.a.tolist()
    class Boxes:
        def __init__(s, xyxy, ids):
            s.xyxy = T(xyxy); s.conf = T([0.9]*len(xyxy)); s.id = T(ids) if ids is not None else None
        def __len__(s): return len(s.xyxy.a)
    class Res: 
        def __init__(s, b): s.boxes = b
    class FakeModel:
        script = ([], None)   # (xyxy, ids) hiện tại
        def track(s, source, **k): xy, ids = FakeModel.script; return [Res(Boxes(xy, ids))] if len(xy) else [Res(None)]
        predict = track

    d = pd.CameraDetector(camera_index=vid, model=FakeModel())
    # Camera USB offline/recovered: mỗi lần chuyển trạng thái chỉ tạo một sự kiện.
    d._set_camera_health(False, "test offline")
    d._set_camera_health(False, "test offline lặp")
    d._set_camera_health(True)
    health_events = [event["type"] for event in d.get_events()]
    assert health_events.count("camera_offline") == 1, health_events
    assert health_events.count("camera_recovered") == 1, health_events
    d.start()
    t0 = time.time()
    while not d.status()["camera_available"] and time.time() - t0 < 10: time.sleep(0.1)
    st = d.status(); assert st["camera_available"], st
    assert d.wait_for_frame(0, 5) is not None and d.snapshot_jpeg() is not None
    def settle(sec=0.8): time.sleep(sec); return d.status()
    def settle_until(predicate, timeout=4.0):
        deadline = time.time() + timeout
        latest = d.status()
        while time.time() < deadline:
            latest = d.status()
            if predicate(latest):
                return latest
            time.sleep(0.05)
        return latest

    FakeModel.script = ([[250, 150, 400, 400]], [7]); st = settle_until(lambda x: x["person_in_zone"] and x["tracked_person_ids"] == [7])
    assert st["person_in_zone"] and st["tracked_person_ids"] == [7], st
    assert any(event["type"] == "unauthorized_entry" for event in d.get_events()), d.get_events()
    # Evidence is rate-limited independently from event creation; event itself must remain.
    latest_event = d.get_events()[0]
    assert latest_event["event_id"] and latest_event["type"]
    if latest_event.get("evidence_url"):
        evidence_name = latest_event["evidence_url"].rsplit("/", 1)[-1]
        assert os.path.isfile(os.path.join(tmp, "evidence", evidence_name))
    # Bật lại khi người đã ở trong vùng: phải ALARM ngay, không đợi một lần xâm nhập mới.
    d.set_anti_theft(False)
    armed = d.set_anti_theft(True)
    assert armed["alarm_state"] == "ALARM" and 7 in armed["alarm_person_ids"], armed
    assert d.heatmap_jpeg() is not None
    FakeModel.script = ([[250, 20, 400, 120]], [7]); st = settle_until(lambda x: not x["person_in_zone"])
    assert not st["person_in_zone"], st
    FakeModel.script = ([[250, 150, 400, 400]], None); st = settle_until(lambda x: x["person_in_zone"] and x["tracked_person_ids"] == [])       # chưa có ID vẫn phải báo đỏ (lỗi cũ: bỏ qua)
    assert st["person_in_zone"] and st["tracked_person_ids"] == [], st
    FakeModel.script = ([[200, 150, 440, 479]], [8]); st = settle_until(lambda x: x["person_in_zone"] and x["tracked_person_ids"] == [8])        # chân bị cắt
    assert st["person_in_zone"], st
    FakeModel.script = ([[250, 150, 262, 160]], [9]); st = settle_until(lambda x: x["detections"] == 0 and not x["person_in_zone"])        # box quá nhỏ bị lọc
    assert not st["person_in_zone"], st
    print("4. pipeline OK, fps≈", st["fps"], "nguồn:", st["camera_source"])

    # 5. Tự nạp lại zone.json + cảnh báo lệch khung
    pd.save_zone_file([(0.0, 0.0), (0.3, 0.0), (0.3, 0.3), (0.0, 0.3)], (1280, 720))
    FakeModel.script = ([[10, 20, 100, 100]], [11])
    # Chờ đúng điều kiện dữ liệu đã reload VÀ frame mới đã qua pipeline;
    # sleep cố định dễ đọc trúng khoảng trống khi video giả chạm EOF/reopen.
    st = settle_until(lambda x: x["zone_frame_size"] == [1280, 720] and x["person_in_zone"], timeout=8.0)
    assert d.zone[1] == (0.3, 0.0) and st["person_in_zone"], (d.zone, st)
    assert st["zone_frame_size"] == [1280, 720], st
    assert st["zone_warning"], "phải cảnh báo lệch tỉ lệ 16:9 vs 4:3"
    # Lưu lại cùng đa giác nhưng ở độ phân giải vẽ khác: metadata vẫn phải reload.
    pd.save_zone_file([(0.0, 0.0), (0.3, 0.0), (0.3, 0.3), (0.0, 0.3)], (1920, 1080))
    d._zone_check_at = 0.0
    d._maybe_reload_zone(time.monotonic() + 2.0)
    assert d.status()["zone_frame_size"] == [1920, 1080], d.status()
    print("5. hot-reload + aspect warning OK")

    d.stop(); assert not d.running
    print("TẤT CẢ TEST ĐẠT")


def test_wait_for_frame_returns_immediately_when_detector_is_stopped():
    from threading import Condition, Event
    detector = object.__new__(pd.CameraDetector)
    detector._out_cond = Condition()
    detector._stop = Event()
    detector._out_jpeg = b"previous-frame"
    detector._out_seq = 1
    detector._stop.set()
    started = time.monotonic()
    assert detector.wait_for_frame(0, timeout=5.0) is None
    assert time.monotonic() - started < 0.1
