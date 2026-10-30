"""Mở camera USB ngoài một cách bền vững (Windows / Linux / macOS).

Các lỗi của bản cũ mà module này xử lý:
  * Chỉ thử một index (mặc định 0). Máy laptop có webcam trong -> webcam USB ngoài thường là
    index 1 hoặc 2. Giờ có chế độ `auto` (ưu tiên camera ngoài) và công cụ `python -m ai.list_cameras`.
  * Chỉ thử CAP_DSHOW. Giờ thử lần lượt DSHOW -> MSMF -> mặc định (Windows), V4L2 -> mặc định (Linux).
  * Không bỏ vài frame đầu: nhiều webcam trả frame đen/None ngay sau khi mở -> bị coi là "mất camera".
  * Không yêu cầu MJPG: webcam USB 2.0 ở dạng YUY2 chạy rất chậm/không mở được ở 640x480 trên vài máy.
  * Cho phép đưa URL (RTSP/HTTP) hoặc đường dẫn thiết bị (/dev/video2) thay vì số.
"""
from __future__ import annotations

import logging
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

# Phải đặt TRƯỚC khi import cv2: MSMF trên Windows có thể mất hàng chục giây để mở camera nếu bật HW transform.
os.environ.setdefault("OPENCV_VIDEOIO_MSMF_ENABLE_HW_TRANSFORMS", "0")

import cv2  # noqa: E402
import numpy as np  # noqa: E402

logger = logging.getLogger(__name__)
AUTO = "auto"


@dataclass
class OpenedCamera:
    capture: cv2.VideoCapture
    source: int | str
    backend: str
    width: int
    height: int
    first_frame: np.ndarray

    def describe(self) -> str:
        return f"{self.source} ({self.backend}, {self.width}x{self.height})"


def parse_camera_source(value: Any) -> int | str:
    """'auto'/'' -> AUTO, '1' -> 1, 'rtsp://...' hoặc '/dev/video2' -> chuỗi nguyên bản."""
    if value is None:
        return AUTO
    if isinstance(value, bool):
        return AUTO
    if isinstance(value, int):
        return max(0, value)
    text = str(value).strip().strip('"').strip("'")
    if text == "" or text.lower() in {AUTO, "usb", "external"}:
        return AUTO
    if text.isdigit():
        return int(text)
    return text


def _backends(source: int | str) -> list[tuple[str, int]]:
    if isinstance(source, str):
        return [("ANY", cv2.CAP_ANY)]
    if os.name == "nt":
        names = ("CAP_DSHOW", "CAP_MSMF", "CAP_ANY")
    elif sys.platform == "darwin":
        names = ("CAP_AVFOUNDATION", "CAP_ANY")
    else:
        names = ("CAP_V4L2", "CAP_ANY")
    return [(name[4:], getattr(cv2, name)) for name in names if hasattr(cv2, name)]


def _read_valid_frame(cap: cv2.VideoCapture, warmup_frames: int, max_seconds: float) -> np.ndarray | None:
    """Bỏ các frame khởi động, trả về frame hợp lệ cuối cùng (chấp nhận cả phòng tối)."""
    deadline = time.monotonic() + max_seconds
    last_valid: np.ndarray | None = None
    for _ in range(max(1, warmup_frames)):
        ok, frame = cap.read()
        if ok and frame is not None and frame.size:
            last_valid = frame
            if float(frame.mean()) >= 3.0:  # đã có hình thật, không phải frame đen khởi động
                return frame
        elif time.monotonic() > deadline:
            break
        if time.monotonic() > deadline:
            break
        time.sleep(0.02)
    return last_valid


def _try_open(source: int | str, backend_name: str, backend_id: int, width: int, height: int,
              fourcc: str | None, warmup_frames: int) -> tuple[OpenedCamera | None, bool]:
    """Trả về (camera hoặc None, thiết bị_có_mở_được)."""
    cap: cv2.VideoCapture | None = None
    try:
        cap = cv2.VideoCapture(source, backend_id)
        if not cap.isOpened():
            cap.release()
            return None, False
        if isinstance(source, int) or str(source).startswith("/dev/"):  # chỉ chỉnh thông số với webcam thật
            if fourcc:
                cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*fourcc))
            if width > 0:
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            if height > 0:
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        frame = _read_valid_frame(cap, warmup_frames, max_seconds=4.0)
        if frame is None:
            cap.release()
            return None, True
        h, w = frame.shape[:2]
        return OpenedCamera(cap, source, backend_name, w, h, frame), True
    except Exception:  # noqa: BLE001
        logger.exception("Lỗi khi mở camera %s bằng %s", source, backend_name)
        if cap is not None:
            cap.release()
        return None, False


def _scan_order(max_index: int, prefer_external: bool) -> list[int]:
    indices = list(range(max_index + 1))
    if prefer_external and len(indices) > 1:
        return indices[1:] + [0]  # webcam trong của laptop thường là 0, camera USB ngoài là 1, 2...
    return indices


def open_camera(source: int | str = AUTO, *, width: int = 640, height: int = 480,
                fourcc: str | None = "MJPG", scan_max_index: int = 5, fallback_scan: bool | None = None,
                prefer_external: bool = True, warmup_frames: int = 15,
                skip_indices: Iterable[int] = ()) -> OpenedCamera | None:
    """Mở camera theo `source`. Trả về None nếu không mở được cái nào.

    source: số (index), AUTO (tự dò), hoặc chuỗi (URL/đường dẫn).
    fallback_scan: nếu index chỉ định không mở được thì dò các index khác. Mặc định chỉ bật với AUTO,
                   để khi bạn ghi rõ CAMERA_INDEX=1 hệ thống không âm thầm chuyển sang webcam laptop.
    """
    source = parse_camera_source(source)
    skip = set(skip_indices)
    if isinstance(source, str) and source != AUTO:
        candidates: list[int | str] = [source]
    elif source == AUTO:
        candidates = [i for i in _scan_order(scan_max_index, prefer_external) if i not in skip]
    else:
        candidates = [source]
        if fallback_scan:
            candidates += [i for i in _scan_order(scan_max_index, prefer_external) if i != source and i not in skip]

    for candidate in candidates:
        for backend_name, backend_id in _backends(candidate):
            cam, device_opened = _try_open(candidate, backend_name, backend_id, width, height, fourcc, warmup_frames)
            if cam is None and device_opened and fourcc:
                # Mở được nhưng không ra hình -> thử lại không ép MJPG (một số camera/driver không hỗ trợ).
                cam, _ = _try_open(candidate, backend_name, backend_id, width, height, None, warmup_frames)
            if cam is not None:
                logger.info("Đã mở camera %s", cam.describe())
                return cam
            logger.debug("Camera %s qua %s: không dùng được", candidate, backend_name)
    return None


def list_cameras(max_index: int = 5, *, width: int = 640, height: int = 480,
                 skip: Iterable[int] = (), save_dir: str | Path | None = None) -> list[dict[str, Any]]:
    """Dò các index camera đang dùng được; tùy chọn lưu ảnh chụp thử để bạn biết index nào là camera nào."""
    found: list[dict[str, Any]] = []
    skipped = set(skip)
    out_dir = Path(save_dir) if save_dir else None
    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)
    for index in range(max_index + 1):
        if index in skipped:
            found.append({"index": index, "ok": None, "note": "đang được KhoAI sử dụng"})
            continue
        entry: dict[str, Any] = {"index": index, "ok": False}
        for backend_name, backend_id in _backends(index):
            cam, _ = _try_open(index, backend_name, backend_id, width, height, None, warmup_frames=10)
            if cam is None:
                continue
            entry.update(ok=True, backend=backend_name, width=cam.width, height=cam.height,
                         brightness=round(float(cam.first_frame.mean()), 1))
            if out_dir:
                path = out_dir / f"camera_{index}.jpg"
                cv2.imwrite(str(path), cam.first_frame)
                entry["snapshot"] = str(path)
            cam.capture.release()
            break
        found.append(entry)
    return found
