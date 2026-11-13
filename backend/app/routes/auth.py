"""Compatibility facade composing authentication and administrator routers."""
from __future__ import annotations

from typing import Any, Protocol
from fastapi import APIRouter

from .auth_sessions import create_auth_session_router
from .admin_users import create_admin_users_router


class AuthRouteServices(Protocol):
    db_session: Any
    monotonic: Any
    epoch_time: Any
    auth_lock: Any
    auth_failures: Any
    auth_rate_window: int
    auth_rate_limit: int
    dummy_password_hash: Any
    verify_credential_hash: Any
    record_auth_failure: Any
    now_business: Any
    hash_credential: Any
    session_digest: Any
    session_seconds: int
    load_session: Any
    require_admin: Any


def create_auth_router(services: AuthRouteServices) -> APIRouter:
    router = APIRouter()
    router.include_router(create_auth_session_router(services))
    router.include_router(create_admin_users_router(services))
    return router
