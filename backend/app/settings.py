"""Centralized runtime paths and environment-derived settings."""
from __future__ import annotations

import os
import re
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = Path(os.getenv("DB_PATH", str(ROOT / "data" / "khoai.sqlite3")))
BUSINESS_TZ = ZoneInfo(os.getenv("BUSINESS_TIMEZONE", "Asia/Ho_Chi_Minh"))
UID_RE = re.compile(r"^[0-9A-Fa-f]{4,20}$")
CAMERA_AUTOSTART = os.getenv("KHOAI_CAMERA_AUTOSTART", "1") != "0"
EXTERNAL_TIME_SCALE = int(os.getenv("KHOAI_EXTERNAL_TIME_SCALE", "60"))
EXTERNAL_WARN_MINUTES = int(os.getenv("KHOAI_EXTERNAL_WARN_MINUTES", "10"))
EXTERNAL_SEVERE_MINUTES = int(os.getenv("KHOAI_EXTERNAL_SEVERE_MINUTES", "20"))
