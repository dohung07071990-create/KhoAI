"""Small, explicit Demo/Strict profile defaults; environment variables override them."""
from __future__ import annotations

import json
import os
from pathlib import Path
from functools import lru_cache

PROFILE_DIR = Path(__file__).resolve().parent.parent / "config" / "profiles"
ENV_TO_SETTING = {
    "KHOAI_ENTRY_GRACE_SECONDS": "entry_grace_seconds",
    "KHOAI_WRONG_ZONE_GRACE_SECONDS": "wrong_zone_grace_seconds",
    "KHOAI_PRESENCE_RELEASE_SECONDS": "presence_release_seconds",
    "KHOAI_RFID_TICKET_SECONDS": "rfid_ticket_seconds",
    "KHOAI_SUSPICIOUS_SECONDS": "suspicious_seconds",
    "KHOAI_SUSPICIOUS_APPROACH_COUNT": "suspicious_approach_count",
    "KHOAI_HANDOVER_MAX_GAP_SECONDS": "handover_max_gap_seconds",
    "KHOAI_HANDOVER_MATCH_RADIUS": "handover_match_radius",
    "KHOAI_HANDOVER_EXCLUSION_RADIUS": "handover_exclusion_radius",
    "KHOAI_HANDOVER_RAW_INSIDE_CONFIRM_SECONDS": "handover_raw_inside_confirm_seconds",
    "KHOAI_HANDOVER_EDGE_MARGIN_RATIO": "handover_edge_margin_ratio",
}


def profile_name() -> str:
    name = os.getenv("KHOAI_PROFILE", "demo").strip().lower() or "demo"
    if name not in {"demo", "strict"}:
        raise ValueError("KHOAI_PROFILE chỉ nhận 'demo' hoặc 'strict'.")
    return name


@lru_cache(maxsize=2)
def _load_profile(name: str) -> dict:
    path = PROFILE_DIR / f"{name}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("name") != name or not isinstance(data.get("settings"), dict):
        raise ValueError(f"Profile không hợp lệ: {path}")
    return data


def profile_settings() -> dict:
    return dict(_load_profile(profile_name())["settings"])


def profile_env_default(env_name: str, fallback):
    """Return a profile default only when caller did not supply this env var."""
    if env_name in os.environ:
        return fallback
    setting = ENV_TO_SETTING.get(env_name)
    return profile_settings().get(setting, fallback) if setting else fallback
