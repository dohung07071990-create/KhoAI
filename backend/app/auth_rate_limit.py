"""Shared in-memory rate-limit primitives for administrator authentication.

The module is deliberately policy-light: the auth facade supplies its existing
lock, failure map, limits and credential matcher. This keeps legacy monkeypatch
and dependency-injection points stable while isolating throttling mechanics.
"""
from __future__ import annotations

import time
from typing import Callable

from fastapi import HTTPException, Request


def record_auth_failure(
    ip: str,
    *,
    lock,
    failures: dict[str, list[float]],
    window: int,
) -> None:
    now = time.monotonic()
    with lock:
        for key in list(failures):
            fresh = [stamp for stamp in failures[key] if now - stamp < window]
            if fresh:
                failures[key] = fresh
            else:
                failures.pop(key, None)
        values = [stamp for stamp in failures[ip] if now - stamp < window]
        values.append(now)
        failures[ip] = values


def check_admin_header(
    request: Request,
    supplied: str | None,
    expected: str,
    *,
    lock,
    failures: dict[str, list[float]],
    limit: int,
    window: int,
    credential_matches: Callable[[str | None, str], bool],
    record_failure: Callable[[str], None],
) -> bool:
    ip = request.client.host if request.client else "unknown"
    now = time.monotonic()
    with lock:
        for key in list(failures):
            fresh = [stamp for stamp in failures[key] if now - stamp < window]
            if fresh:
                failures[key] = fresh
            else:
                failures.pop(key, None)
        values = failures.get(ip, [])
        if len(values) >= limit:
            raise HTTPException(status_code=429, detail="Quá nhiều lần xác thực thất bại; thử lại sau.")
    if supplied is None:
        return False
    if not credential_matches(supplied, expected):
        record_failure(ip)
        return False
    with lock:
        failures.pop(ip, None)
    return True
