"""Device API-key authentication and per-client failure throttling.

This module owns the device credential policy independently of admin sessions.
The public dependency is re-exported by :mod:`backend.app.auth` for compatibility.
"""
from __future__ import annotations

import os
import json
import threading
import time
from collections import defaultdict

from fastapi import Header, HTTPException, Request

from .security_credentials import _credential_matches

DEVICE_KEY_FAIL_LIMIT = max(3, int(os.getenv("KHOAI_DEVICE_KEY_FAIL_LIMIT", "8")))
DEVICE_KEY_FAIL_WINDOW = max(10, int(os.getenv("KHOAI_DEVICE_KEY_FAIL_WINDOW", "60")))
_device_key_failures: dict[str, list[float]] = defaultdict(list)
_device_key_lock = threading.Lock()


def _valid_device_secret(value: str) -> bool:
    markers = ("thay-bang", "change-me", "changeme", "example", "replace_with", "your-")
    return len(value) >= 32 and not any(marker in value.lower() for marker in markers)


def require_device_key(
    request: Request,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    x_device_id: str | None = Header(default=None, alias="X-Device-ID"),
) -> None:
    key_registry = os.getenv("KHOAI_DEVICE_API_KEYS_JSON", "").strip()
    if key_registry:
        try:
            parsed = json.loads(key_registry)
            secrets_by_device = {str(key): str(value).strip() for key, value in parsed.items()} if isinstance(parsed, dict) else {}
        except (TypeError, ValueError):
            secrets_by_device = {}
        if not secrets_by_device or any(not key or not _valid_device_secret(value) for key, value in secrets_by_device.items()):
            raise HTTPException(status_code=503, detail="Cấu hình API key thiết bị không hợp lệ; endpoint thiết bị đã bị khóa.")
        expected = secrets_by_device.get((x_device_id or "").strip(), "")
    else:
        expected = os.getenv("KHOAI_API_KEY", "").strip()
    if not key_registry and not _valid_device_secret(expected):
        raise HTTPException(
            status_code=503,
            detail="KHOAI_API_KEY chưa được cấu hình bằng khóa riêng tối thiểu 32 ký tự; endpoint thiết bị bị khóa.",
        )

    ip = request.client.host if request.client else "unknown"
    now = time.monotonic()
    with _device_key_lock:
        recent = [stamp for stamp in _device_key_failures[ip] if now - stamp < DEVICE_KEY_FAIL_WINDOW]
        _device_key_failures[ip] = recent
        if len(recent) >= DEVICE_KEY_FAIL_LIMIT:
            raise HTTPException(
                status_code=429,
                detail="Quá nhiều lần xác thực thiết bị thất bại; thử lại sau.",
            )

    comparison_secret = expected or ("0" * 64)
    if not _credential_matches(x_api_key, comparison_secret) or not expected:
        with _device_key_lock:
            _device_key_failures[ip].append(now)
        raise HTTPException(status_code=401, detail="API key không hợp lệ hoặc chưa được cung cấp.")

    with _device_key_lock:
        _device_key_failures.pop(ip, None)
