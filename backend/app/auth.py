"""Authentication, session and device-key security primitives."""
from __future__ import annotations

import asyncio
import logging
import os
import secrets
import threading
import time
from collections import OrderedDict, defaultdict
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable

from fastapi import Depends, Header, HTTPException, Request
from fastapi.responses import Response

from .database import db_session as _db_session
from .settings import DB_PATH, BUSINESS_TZ
from .security_credentials import (
    _credential_matches, _hash_password, _verify_password, _validate_admin_secret,
)
from .session_tokens import _session_digest
from .uid_normalization import normalize_uid
from .auth_rate_limit import record_auth_failure, check_admin_header

SESSION_SECONDS = max(300, int(os.getenv("KHOAI_ADMIN_SESSION_SECONDS", str(8 * 60 * 60))))
AUTH_RATE_LIMIT = max(3, int(os.getenv("KHOAI_AUTH_FAIL_LIMIT", "5")))
AUTH_RATE_WINDOW = max(10, int(os.getenv("KHOAI_AUTH_FAIL_WINDOW", "60")))
_auth_lock = threading.Lock()
_auth_failures: dict[str, list[float]] = defaultdict(list)

logger = logging.getLogger("khoai")
_database_path_provider: Callable[[], Path] = lambda: DB_PATH
_db_session_provider: Callable[[], Any] | None = None

def set_database_path_provider(provider: Callable[[], Path]) -> None:
    """Allow the application bootstrap to supply its current configured DB path."""
    global _database_path_provider
    _database_path_provider = provider

def set_db_session_provider(provider: Callable[[], Any]) -> None:
    """Keep database access injectable through the application compatibility layer."""
    global _db_session_provider
    _db_session_provider = provider

def db_session() -> Any:
    if _db_session_provider is not None:
        return _db_session_provider()
    return _db_session(_database_path_provider())

def now_business() -> str:
    return datetime.now(BUSINESS_TZ).isoformat(timespec="seconds")

def today_business() -> str:
    return datetime.now(BUSINESS_TZ).date().isoformat()

@lru_cache(maxsize=1)
def _dummy_password_hash() -> str:
    return _hash_password("KhoAI-dummy-password-never-valid")



def _load_session(session_id: str | None) -> dict[str, Any] | None:
    digest = _session_digest(session_id)
    if not digest:
        return None
    try:
        with db_session() as db:
            row = db.execute("""SELECT s.expires_at,s.operator_name,s.user_id,s.role,
                    u.role AS current_role,u.active AS user_active,u.username
                FROM admin_sessions s LEFT JOIN admin_users u ON u.user_id=s.user_id
                WHERE s.session_id=?""", (digest,)).fetchone()
            if not row:
                return None
            if float(row["expires_at"]) <= time.time():
                db.execute("DELETE FROM admin_sessions WHERE session_id=?", (digest,))
                return None
            # Account-backed sessions always use the current DB role and active flag.
            if row["user_id"] is not None:
                if row["user_active"] != 1:
                    db.execute("DELETE FROM admin_sessions WHERE session_id=?", (digest,))
                    return None
                role = str(row["current_role"] or "")
            else:
                # Shared-token legacy sessions have no user row and are admin-only.
                role = "admin"
            return {"role": role, "operator_name": row["operator_name"], "user_id": row["user_id"],
                    "username": row["username"] if "username" in row.keys() else None}
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Không thể xác minh session quản trị")
        raise HTTPException(status_code=503, detail="Không thể xác minh phiên đăng nhập; hệ thống tạm khóa truy cập.") from exc


def _session_valid(session_id: str | None) -> bool:
    return _load_session(session_id) is not None


class SessionValidationUnavailable(RuntimeError):
    """Session state could not be checked because the backing store is unavailable."""


def _session_digest_valid(digest: str | None) -> bool:
    """Return False only for an invalid session; raise when SQLite cannot verify it."""
    if not digest:
        return False
    try:
        with db_session() as db:
            row = db.execute("""SELECT s.expires_at,s.user_id,u.active,u.role
                FROM admin_sessions s LEFT JOIN admin_users u ON u.user_id=s.user_id
                WHERE s.session_id=?""", (digest,)).fetchone()
            if not row or float(row["expires_at"]) <= time.time():
                return False
            if row["user_id"] is not None and row["active"] != 1:
                return False
            return row["user_id"] is None or row["role"] in {"admin", "viewer"}
    except Exception as exc:
        logger.warning("Không thể xác minh session stream do backend tạm thời không khả dụng: %s", type(exc).__name__)
        raise SessionValidationUnavailable("Session validation temporarily unavailable") from exc


# Cache only definitive results. Transient database failures are never cached as
# invalid sessions; callers can retry or close with service-unavailable semantics.
_SESSION_CACHE_TTL_SECONDS = 2.0
_SESSION_CACHE_MAX_ENTRIES = 2048
_session_validation_cache: OrderedDict[tuple[str, int], tuple[float, bool]] = OrderedDict()
_session_validation_cache_lock = threading.Lock()


async def _session_digest_valid_cached(
    digest: str | None,
    validator=None,
) -> bool:
    if not digest:
        return False

    validate = validator or _session_digest_valid
    # Include validator identity so injected compatibility/test validators never
    # reuse a result produced by a different validation function.
    cache_key = (digest, id(validate))
    now = time.monotonic()
    with _session_validation_cache_lock:
        cached = _session_validation_cache.get(cache_key)
        if cached is not None:
            if now - cached[0] < _SESSION_CACHE_TTL_SECONDS:
                _session_validation_cache.move_to_end(cache_key)
                return cached[1]
            _session_validation_cache.pop(cache_key, None)

    valid = await asyncio.to_thread(validate, digest)
    confirmed_at = time.monotonic()
    with _session_validation_cache_lock:
        _session_validation_cache[cache_key] = (confirmed_at, valid)
        _session_validation_cache.move_to_end(cache_key)
        while len(_session_validation_cache) > _SESSION_CACHE_MAX_ENTRIES:
            _session_validation_cache.popitem(last=False)
    return valid


def _record_auth_failure(ip: str) -> None:
    """Compatibility wrapper around the shared admin-auth rate limiter."""
    record_auth_failure(
        ip, lock=_auth_lock, failures=_auth_failures, window=AUTH_RATE_WINDOW,
    )


def _check_admin_header(request: Request, supplied: str | None, expected: str) -> bool:
    """Preserve the historical auth facade and its injectable dependencies."""
    return check_admin_header(
        request, supplied, expected,
        lock=_auth_lock,
        failures=_auth_failures,
        limit=AUTH_RATE_LIMIT,
        window=AUTH_RATE_WINDOW,
        credential_matches=_credential_matches,
        record_failure=_record_auth_failure,
    )


def _issue_admin_session(response: Response, request: Request) -> str:
    session_id = secrets.token_urlsafe(32)
    digest = _session_digest(session_id)
    if digest is None:
        raise RuntimeError("Không thể tạo mã hash cho admin session")
    now = time.time()
    operator_name = (request.headers.get("X-Operator-Name") or "Quản trị viên (token dùng chung)").strip()[:80]
    if not operator_name:
        operator_name = "Quản trị viên (token dùng chung)"
    ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "")[:300]
    with db_session() as db:
        db.execute("DELETE FROM admin_sessions WHERE expires_at<=?", (now,))
        db.execute("INSERT INTO admin_sessions(session_id,created_at,expires_at,operator_name,user_id,role) VALUES(?,?,?,?,NULL,'admin')",
                   (digest, now, now + SESSION_SECONDS, operator_name))
        db.execute("""INSERT INTO system_access_logs(event_at,event_type,operator_name,session_id,ip_address,user_agent,details)
                      VALUES(?,?,?,?,?,?,?)""",
                   (now_business(), "LOGIN", operator_name, digest[:16], ip, user_agent,
                    "Đăng nhập bằng token quản trị dùng chung; tên người vận hành do người dùng tự khai báo."))
    response.set_cookie(key="khoai_admin_session", value=session_id, httponly=True,
                        secure=request.url.scheme == "https", samesite="strict", path="/", max_age=SESSION_SECONDS)
    return digest


def _authenticate(request: Request, response: Response, x_admin_token: str | None, admin_only: bool) -> None:
    cookie = request.cookies.get("khoai_admin_session")
    session = _load_session(cookie)
    if session:
        request.state.khoai_role = session["role"]
        request.state.khoai_operator_name = session.get("operator_name")
        request.state.khoai_user_id = session.get("user_id")
        request.state.khoai_session_digest = _session_digest(cookie)
        if admin_only and session["role"] != "admin":
            raise HTTPException(status_code=403, detail="Tài khoản chỉ có quyền xem; chức năng này dành cho admin.")
        return
    expected = os.getenv("KHOAI_ADMIN_TOKEN", "").strip()
    if not expected:
        if cookie:
            raise HTTPException(status_code=401, detail="Phiên đăng nhập không còn hợp lệ; vui lòng đăng nhập lại.")
        raise HTTPException(status_code=503, detail="Chưa cấu hình tài khoản quản trị hoặc KHOAI_ADMIN_TOKEN; API bị khóa an toàn.")
    _validate_admin_secret(expected)
    if _check_admin_header(request, x_admin_token, expected):
        digest = _issue_admin_session(response, request)
        request.state.khoai_role = "admin"
        request.state.khoai_operator_name = request.headers.get("X-Operator-Name") or "Quản trị viên (token dùng chung)"
        request.state.khoai_user_id = None
        request.state.khoai_session_digest = digest
        return
    raise HTTPException(status_code=401, detail="Thiếu hoặc sai phiên đăng nhập.")


def require_session(
    request: Request, response: Response,
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
) -> None:
    _authenticate(request, response, x_admin_token, admin_only=False)


def require_admin_role(
    request: Request, response: Response,
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
) -> None:
    _authenticate(request, response, x_admin_token, admin_only=True)


# Backward-compatible dependency name; all existing admin-protected routes remain admin-only.
require_admin = require_admin_role
require_admin_query = require_session


from .device_auth import (
    DEVICE_KEY_FAIL_LIMIT, DEVICE_KEY_FAIL_WINDOW,
    _device_key_failures, _device_key_lock, _valid_device_secret, require_device_key,
)
