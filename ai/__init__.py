"""Gói AI của KhoAI (camera USB + YOLO + ByteTrack + vùng cấm).

Phần khởi tạo (init) của gói:
  1. Nạp `.env` TRƯỚC khi bất kỳ module nào đọc biến môi trường.
  2. Không import cv2/ultralytics ở đây, để backend vẫn chạy được trên máy
     chưa cài thư viện AI (các import nặng chỉ diễn ra khi truy cập `detector`).

Dùng:
    from ai import detector            # singleton CameraDetector
    from ai import CameraDetector      # hoặc tạo bản riêng
"""
from __future__ import annotations

from typing import Any

from .envfile import load_env_file

__version__ = "0.3.0"
__all__ = ["detector", "CameraDetector", "load_env_file", "__version__"]

load_env_file()


def __getattr__(name: str) -> Any:  # import lười: chỉ nạp cv2/YOLO khi thật sự cần
    if name in {"detector", "CameraDetector"}:
        from . import person_detector

        return getattr(person_detector, name)
    raise AttributeError(f"module 'ai' has no attribute {name!r}")
