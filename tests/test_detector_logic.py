"""Chạy: python tests/test_detector_logic.py  (không cần camera thật, không cần ultralytics)."""
import os, sys, tempfile, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
tmp = tempfile.mkdtemp()
os.environ["KHOAI_ZONE_FILE"] = os.path.join(tmp, "zone.json")
os.environ["KHOAI_CAMERA_EVIDENCE_DIR"] = os.path.join(tmp, "evidence")
os.environ["KHOAI_ENTER_FRAMES"] = "2"
os.environ["KHOAI_EXIT_FRAMES"] = "3"

import cv2, numpy as np
from ai import person_detector as pd
from ai.camera_utils import parse_camera_source, open_camera, list_cameras
from ai.envfile import _parse_line

W, H = 640, 480
poly = pd.zone_to_pixels(pd.DEFAULT_ZONE, W, H)

# 1. Luật vùng
assert pd.is_box_in_zone((250, 150, 400, 400), (W, H), poly)            # chân trong vùng
assert not pd.is_box_in_zone((250, 20, 400, 150), (W, H), poly)         # chân ở trên vùng (ngoài)
assert not pd.is_box_in_zone((0, 150, 20, 300), (W, H), poly)           # sát mép trái, ngoài
assert pd.is_box_in_zone((200, 150, 440, 479), (W, H), poly)            # chân bị cắt đáy khung -> vẫn trong (lỗi cũ: False)
assert not pd.is_box_in_zone((200, 150, 440, 479), (W, H), poly, truncated_fallback=False)  # đúng hành vi cũ
mask = np.zeros((H, W), np.uint8); cv2.fillPoly(mask, [np.round(poly).astype(np.int32).reshape(-1,1,2)], 255)
assert pd.is_box_in_zone((250, 150, 400, 400), (W, H), poly, "overlap", mask, 0.3)
assert not pd.is_box_in_zone((250, 20, 400, 120), (W, H), poly, "overlap", mask, 0.3)
print("1. luật vùng OK")

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
assert d.get_events()[0]["type"] == "unauthorized_entry"
assert d.get_events()[0].get("evidence_url", "").startswith("/api/camera/evidence/")
assert os.path.isfile(os.path.join(tmp, "evidence", d.get_events()[0]["event_id"] + ".jpg"))
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
FakeModel.script = ([[10, 20, 100, 100]], [11]); time.sleep(2.5); st = d.status()
assert d.zone[1] == (0.3, 0.0) and st["person_in_zone"], (d.zone, st)
assert st["zone_warning"], "phải cảnh báo lệch tỉ lệ 16:9 vs 4:3"
print("5. hot-reload OK")

d.stop(); assert not d.running
print("TẤT CẢ TEST ĐẠT")
