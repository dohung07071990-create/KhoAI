"""Telegram environment configuration and adapter dependency contracts."""
from __future__ import annotations

import logging
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Callable

logger = logging.getLogger("khoai.telegram")


@dataclass(frozen=True)
class TelegramConfig:
    token: str
    allowed_chat_ids: frozenset[int]
    poll_timeout: int = 25
    notify_interval: float = 3.0
    max_send_attempts: int = 0  # retained for compatibility; transient retries are unbounded
    evidence_ttl_seconds: int = 1800
    auth_probe_interval: int = 60
    warning_summary_after_seconds: int = 7200
    api_base: str = "https://api.telegram.org"


def telegram_enabled(env: Mapping[str, str] | None = None) -> bool:
    """One fail-closed parser shared by bot startup and admin status."""
    env = os.environ if env is None else env
    return str(env.get("TELEGRAM_ENABLED", "0")).strip().lower() in {"1", "true", "yes", "on"}


def load_config(env: Mapping[str, str] | None = None) -> TelegramConfig | None:
    env = os.environ if env is None else env
    if not telegram_enabled(env):
        return None
    token = env.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        return None
    ids: set[int] = set()
    for item in re.split(r"[,;]", env.get("TELEGRAM_ALLOWED_CHAT_IDS", "")):
        item = item.strip()
        if item:
            try:
                parsed = int(item)
                if parsed > 0:
                    ids.add(parsed)
                else:
                    logger.warning("Chỉ chấp nhận Telegram private chat ID dương")
            except ValueError:
                logger.warning("Bỏ qua một giá trị TELEGRAM_ALLOWED_CHAT_IDS không hợp lệ")
    if not ids:
        logger.warning("Telegram đã cấu hình token nhưng chưa có allowlist; bot không khởi chạy")
        return None
    try:
        poll_timeout = max(1, min(50, int(env.get("TELEGRAM_POLL_TIMEOUT", "25"))))
        notify_interval = max(1.0, float(env.get("TELEGRAM_NOTIFY_INTERVAL", "3")))
        evidence_ttl = max(60, int(env.get("TELEGRAM_EVIDENCE_TTL_SECONDS", "1800")))
        warning_summary_after = max(300, int(env.get("TELEGRAM_WARNING_SUMMARY_AFTER_SECONDS", "7200")))
    except (TypeError, ValueError):
        logger.warning("Cấu hình polling Telegram không hợp lệ; dùng mặc định")
        poll_timeout, notify_interval, evidence_ttl, warning_summary_after = 25, 3.0, 1800, 7200
    return TelegramConfig(token=token, allowed_chat_ids=frozenset(ids),
                          poll_timeout=poll_timeout, notify_interval=notify_interval,
                          evidence_ttl_seconds=evidence_ttl,
                          warning_summary_after_seconds=warning_summary_after)


@dataclass
class TelegramContext:
    status: Callable[[], dict[str, Any]]
    alerts: Callable[[int], list[dict[str, Any]]]
    acknowledge: Callable[[int, str], bool]
    acknowledge_all: Callable[[str], int]
    snapshot: Callable[[], bytes | None]
    evidence: Callable[[int], dict[str, Any]]
    discover_events: Callable[[int, int], int]
    due_items: Callable[[int, int], list[dict[str, Any]]]
    mark_text: Callable[[int, int, int], None]
    retry_text: Callable[[int, int, str, float, bool], None]
    mark_photo: Callable[[int, int, str, int | None, str | None, float], None]
    lease: Callable[[str, str, int], bool]
    retry_permanent: Callable[[int, int], bool]
    ops_status: Callable[[], dict[str, Any]]
    runtime_state: Callable[[str, str], None]
