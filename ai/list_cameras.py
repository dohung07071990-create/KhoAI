"""Liệt kê camera và lưu ảnh chụp thử để biết CAMERA_INDEX nào là camera USB ngoài.

    python -m ai.list_cameras              # dò index 0..5
    python -m ai.list_cameras --max 8

Dừng server KhoAI trước khi chạy (một camera chỉ một chương trình dùng được).
Ảnh chụp lưu ở ai/camera_probe/camera_<index>.jpg -> mở ảnh nào thấy đúng hình camera ngoài thì đặt
CAMERA_INDEX bằng số đó trong .env.
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ai.camera_utils import list_cameras  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Dò camera cho KhoAI")
    parser.add_argument("--max", type=int, default=5, help="index lớn nhất cần dò (mặc định 5)")
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING)
    out_dir = Path(__file__).resolve().parent / "camera_probe"
    cameras = list_cameras(args.max, save_dir=out_dir)
    working = [c for c in cameras if c.get("ok")]
    for c in cameras:
        if c.get("ok"):
            print(f"[OK ] index {c['index']}: {c['width']}x{c['height']} qua {c['backend']}, độ sáng TB {c['brightness']}"
                  f" -> {c.get('snapshot', '')}")
        else:
            print(f"[---] index {c['index']}: không mở được")
    if working:
        print(f"\nXem ảnh trong {out_dir}, rồi đặt CAMERA_INDEX=<số> trong .env (hoặc để CAMERA_INDEX=auto).")
    else:
        print("\nKhông tìm thấy camera nào. Kiểm tra: cắm lại cổng USB khác, tắt app khác đang dùng camera "
              "(Zoom/Teams/Camera app), và (Windows) Settings > Privacy > Camera > cho phép ứng dụng desktop.")


if __name__ == "__main__":
    main()
