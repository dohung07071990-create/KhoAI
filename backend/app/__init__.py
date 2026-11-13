"""Ứng dụng FastAPI của KhoAI. Xem `backend/app/main.py` (hàm `lifespan` là phần khởi tạo chính)."""
from __future__ import annotations

from pathlib import Path

APP_NAME = "KhoAI"
APP_VERSION = (Path(__file__).resolve().parents[2] / "VERSION.txt").read_text(encoding="utf-8").strip()
