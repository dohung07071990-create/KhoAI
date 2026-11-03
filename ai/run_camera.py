"""Xem luồng camera đã phân tích trong cửa sổ OpenCV; nhấn q để thoát.

    python -m ai.run_camera          (hoặc: python ai/run_camera.py)

Dừng server KhoAI trước khi chạy vì một camera chỉ một chương trình dùng được.
"""
from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from ai.person_detector import detector  # noqa: E402


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    detector.start()
    last_seq, last_report = 0, 0.0
    try:
        while True:
            result = detector.wait_for_frame(last_seq, timeout=0.5)
            if result is None:
                if time.monotonic() - last_report > 3:
                    st = detector.status()
                    print(f"Đang chờ camera... nguồn={st['camera_source']} lỗi={st['camera_error'] or st['model_error']}")
                    last_report = time.monotonic()
                if cv2.waitKey(50) & 0xFF == ord("q"):
                    break
                continue
            last_seq, jpeg = result
            frame = cv2.imdecode(np.frombuffer(jpeg, dtype=np.uint8), cv2.IMREAD_COLOR)
            if frame is None:
                continue
            cv2.imshow("KhoAI - press q to quit", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    except KeyboardInterrupt:
        pass
    finally:
        detector.stop()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
