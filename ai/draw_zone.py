"""Vẽ vùng cấm bằng chuột và lưu vào ai/zone.json (tọa độ chuẩn hóa 0–1 + kích thước khung).

Ba cách chạy:
  1) Mở camera trực tiếp (phải TẮT server trước):
        python -m ai.draw_zone
  2) Lấy ảnh từ server đang chạy rồi gửi vùng lên server (KHÔNG cần tắt server, khung nhìn khớp 100%):
        python -m ai.draw_zone --server http://127.0.0.1:3000
  3) Vẽ trên một ảnh có sẵn:
        python -m ai.draw_zone --image anh_kho.jpg

Phím: chuột trái = thêm điểm | U = bỏ điểm cuối | C = xóa hết | S = lưu | Q/Esc = thoát.
Mẹo: vẽ vùng theo MẶT SÀN (nơi chân người chạm đất), không vẽ theo chiều cao người.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from ai.camera_utils import open_camera, parse_camera_source  # noqa: E402
from ai.person_detector import (FRAME_HEIGHT, FRAME_WIDTH, CAMERA_FOURCC, ZONE_FILE, load_zone_file,  # noqa: E402
                                save_zone_file, validate_zone)

WINDOW = "KhoAI - Ve vung cam"
points: list[tuple[int, int]] = []


def on_mouse(event, x, y, flags, param):
    if event == cv2.EVENT_LBUTTONDOWN:
        points.append((x, y))


def fetch_snapshot(server: str) -> np.ndarray | None:
    try:
        with urllib.request.urlopen(f"{server.rstrip('/')}/api/camera/snapshot.jpg", timeout=5) as resp:
            data = np.frombuffer(resp.read(), dtype=np.uint8)
        return cv2.imdecode(data, cv2.IMREAD_COLOR)
    except (urllib.error.URLError, OSError, ValueError):
        return None


def push_zone(server: str, normalized: list[list[float]], size: tuple[int, int]) -> None:
    body = json.dumps({"points": normalized, "frame_size": [size[0], size[1]]}).encode()
    req = urllib.request.Request(f"{server.rstrip('/')}/api/camera/zone", data=body, method="PUT",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=5) as resp:
        resp.read()


def main() -> None:
    parser = argparse.ArgumentParser(description="Vẽ vùng cấm KhoAI")
    parser.add_argument("--server", help="URL server đang chạy, ví dụ http://127.0.0.1:3000")
    parser.add_argument("--image", help="vẽ trên ảnh có sẵn thay vì camera")
    parser.add_argument("--camera", help="index/URL camera (mặc định lấy từ CAMERA_INDEX, auto nếu không đặt)")
    args = parser.parse_args()

    import os
    cam = None
    static_frame: np.ndarray | None = None
    if args.image:
        static_frame = cv2.imread(args.image)
        if static_frame is None:
            raise SystemExit(f"Không đọc được ảnh {args.image}")
    elif not args.server:
        source = parse_camera_source(args.camera if args.camera is not None else os.getenv("CAMERA_INDEX", "auto"))
        cam = open_camera(source, width=FRAME_WIDTH, height=FRAME_HEIGHT, fourcc=CAMERA_FOURCC)
        if cam is None:
            raise SystemExit("Không mở được camera. Tắt server KhoAI (nếu đang chạy), chạy `python -m ai.list_cameras` "
                             "để tìm index đúng, hoặc dùng --server để lấy ảnh từ server đang chạy.")
        print(f"Đã mở camera {cam.describe()}")

    saved_zone, _ = load_zone_file()
    cv2.namedWindow(WINDOW)
    cv2.setMouseCallback(WINDOW, on_mouse)
    frame = static_frame
    tick = 0
    try:
        while True:
            if cam is not None:
                ok, f = cam.capture.read()
                if ok and f is not None:
                    frame = f
            elif args.server:
                if tick % 6 == 0:  # ~ mỗi 0,3 giây
                    f = fetch_snapshot(args.server)
                    if f is not None:
                        frame = f
                tick += 1
            if frame is None:
                blank = np.zeros((240, 640, 3), np.uint8)
                cv2.putText(blank, "Dang cho anh tu camera/server...", (20, 120), cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                            (255, 255, 255), 2)
                cv2.imshow(WINDOW, blank)
                if cv2.waitKey(100) & 0xFF in (ord("q"), 27):
                    break
                continue
            h, w = frame.shape[:2]
            preview = frame.copy()
            old = np.asarray([(round(x * (w - 1)), round(y * (h - 1))) for x, y in saved_zone], np.int32)
            cv2.polylines(preview, [old.reshape(-1, 1, 2)], True, (160, 160, 160), 1)  # vùng đã lưu (xám mảnh)
            for p in points:
                cv2.circle(preview, p, 5, (0, 255, 255), -1)
            if len(points) >= 2:
                cv2.polylines(preview, [np.asarray(points, np.int32).reshape(-1, 1, 2)], len(points) >= 3,
                              (0, 0, 255) if len(points) >= 3 else (0, 255, 255), 2)
            cv2.putText(preview, f"{w}x{h} | {len(points)} diem | Click | U undo | C clear | S save | Q quit",
                        (10, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2, cv2.LINE_AA)
            cv2.imshow(WINDOW, preview)
            key = cv2.waitKey(30 if args.server else 1) & 0xFF
            if key == ord("u") and points:
                points.pop()
            elif key == ord("c"):
                points.clear()
                print("Đã xóa các điểm; vẽ lại vùng.")
            elif key in (ord("q"), 27):
                break
            elif key == ord("s"):
                if len(points) < 3:
                    print("Cần ít nhất 3 điểm để tạo vùng.")
                    continue
                normalized = [[round(x / (w - 1), 6), round(y / (h - 1), 6)] for x, y in points]
                try:
                    validate_zone([(x, y) for x, y in normalized])
                except ValueError as exc:
                    print(f"Vùng không hợp lệ: {exc}")
                    continue
                if args.server:
                    try:
                        push_zone(args.server, normalized, (w, h))
                        print(f"Đã gửi vùng lên server {args.server} (và lưu vào {ZONE_FILE}).")
                    except (urllib.error.URLError, OSError) as exc:
                        print(f"Không gửi được lên server: {exc}")
                        continue
                else:
                    save_zone_file([(x, y) for x, y in normalized], (w, h))
                    print(f"Đã lưu vùng giám sát: {ZONE_FILE} (khung {w}x{h}). Server đang chạy sẽ tự nạp lại.")
                break
    finally:
        if cam is not None:
            cam.capture.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
