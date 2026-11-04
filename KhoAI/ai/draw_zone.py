"""Draw a normalized intrusion polygon with the mouse and save it to ai/zone.json.

Stop the KhoAI web server before running this script so it is the only camera owner.
Left-click to add points, S to save (minimum 3 points), C to clear, Q/Esc to quit.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent
OUT = Path(os.getenv("KHOAI_ZONE_FILE", str(ROOT / "zone.json")))
CAMERA_INDEX = int(os.getenv("CAMERA_INDEX", "0"))
points: list[tuple[int, int]] = []


def on_mouse(event, x, y, flags, param):
    if event == cv2.EVENT_LBUTTONDOWN:
        points.append((x, y))


def main() -> None:
    cap = cv2.VideoCapture(CAMERA_INDEX)
    if not cap.isOpened():
        raise RuntimeError(f"Khong mo duoc camera index {CAMERA_INDEX}; thu CAMERA_INDEX=1.")
    cv2.namedWindow("KhoAI - Draw intrusion zone")
    cv2.setMouseCallback("KhoAI - Draw intrusion zone", on_mouse)
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                print("Khong doc duoc frame camera.")
                break
            preview = frame.copy()
            for p in points:
                cv2.circle(preview, p, 5, (0, 255, 255), -1)
            if len(points) >= 2:
                cv2.polylines(preview, [np.asarray(points, dtype=np.int32)], False, (0, 255, 255), 2)
            if len(points) >= 3:
                cv2.polylines(preview, [np.asarray(points, dtype=np.int32)], True, (0, 0, 255), 2)
            cv2.putText(preview, "Click points | S save | C clear | Q quit", (12, 28),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2, cv2.LINE_AA)
            cv2.imshow("KhoAI - Draw intrusion zone", preview)
            key = cv2.waitKey(1) & 0xFF
            if key == ord('s'):
                if len(points) < 3:
                    print("Can it nhat 3 diem de tao vung.")
                    continue
                h, w = frame.shape[:2]
                normalized = [[round(x / (w - 1), 6), round(y / (h - 1), 6)] for x, y in points]
                OUT.parent.mkdir(parents=True, exist_ok=True)
                OUT.write_text(json.dumps({"points": normalized}, indent=2), encoding="utf-8")
                print(f"Da luu vung giam sat: {OUT}")
                break
            if key == ord('c'):
                points.clear()
                print("Da xoa cac diem; ve lai vung.")
            if key in (ord('q'), 27):
                break
    finally:
        cap.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
