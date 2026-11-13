"""Compatibility facade combining incident-record and security-alert routers."""
from __future__ import annotations

from typing import Any
from fastapi import APIRouter

from .incident_records import create_incident_records_router
from .security_alerts import create_security_alerts_router


def create_incident_router(services: Any) -> APIRouter:
    """Keep the historic router factory while composing the two bounded routers."""
    router = APIRouter()
    router.include_router(create_incident_records_router(services))
    router.include_router(create_security_alerts_router(services))
    return router
