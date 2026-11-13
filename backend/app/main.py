"""KhoAI API.

[MODIFIED] Adds card-to-track association, inventory authorization/comparison and persisted alerts.
[MODIFIED] Camera AI remains optional so card/database functions run on low-spec PCs.
"""
from __future__ import annotations

import json
import logging
import mimetypes
import os
import re
import sqlite3
import time
import hmac
import hashlib
import asyncio
import secrets
import threading
from collections import defaultdict
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager, contextmanager
from functools import lru_cache
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterator, cast
from zoneinfo import ZoneInfo

from fastapi import (FastAPI,HTTPException,Query,Header,Depends,Request,WebSocket,WebSocketDisconnect,)
from fastapi.responses import (FileResponse,Response,StreamingResponse,JSONResponse,)
from fastapi.staticfiles import StaticFiles
from starlette.background import BackgroundTask

from .database import connect_db as _connect_db, db_session as _db_session
from .auth import (
    now_business, today_business, _credential_matches, _hash_password, _verify_password,
    _dummy_password_hash, _validate_admin_secret, _session_digest, _load_session,
    _session_valid, SessionValidationUnavailable, _session_digest_valid,
    _session_digest_valid_cached, _record_auth_failure, _check_admin_header,
    _issue_admin_session, _authenticate, require_session, require_admin_role,
    require_admin, require_admin_query, require_device_key, normalize_uid,
    _auth_lock, _auth_failures, _session_validation_cache, _session_digest_valid_cached as _auth_session_digest_valid_cached,
    _session_digest_valid, AUTH_RATE_LIMIT, AUTH_RATE_WINDOW, SESSION_SECONDS,
    set_database_path_provider, set_db_session_provider,
)
set_database_path_provider(lambda: DB_PATH)
set_db_session_provider(lambda: db_session())

# Compatibility facade: retain the main-module patch point without mutating
# the auth module's global validator.
async def _session_digest_valid_cached(digest: str | None) -> bool:
    return await _auth_session_digest_valid_cached(digest, validator=_session_digest_valid)
from .retention import RetentionService
from .services.application_lifecycle import application_lifespan
from .privacy import _mask_uid, _mask_uid_fields, _known_uid_cache, _known_uid_cache_lock, _known_card_uids_for_redaction
from . import privacy as _privacy_module
def _mask_uid_payload(value: Any) -> Any:
    # Preserve the established injection point through an explicit provider.
    return _privacy_module._mask_uid_payload(
        value, known_uids_provider=_known_card_uids_for_redaction,
    )
from .audit import AdminAuditMiddleware
from .settings import (ROOT, DB_PATH, BUSINESS_TZ, UID_RE, CAMERA_AUTOSTART,
                       EXTERNAL_TIME_SCALE, EXTERNAL_WARN_MINUTES, EXTERNAL_SEVERE_MINUTES)
from .schemas import (CardCreate, CardUpdate, RFIDScan, DeviceHeartbeat, SecurityEventInput,
                      AccessCheck, CameraZoneUpdate, CameraAntiTheftUpdate, HomographyCalibrationInput,
                      RFIDEntryROIUpdate, AdminLogin, AdminUserCreate, AdminUserUpdate)


FRONTEND_DIR = ROOT / "frontend"
# Windows MIME registries can omit or misclassify JavaScript modules.
# Register an explicit JavaScript MIME type before StaticFiles serves .js files.
mimetypes.add_type("text/javascript", ".js")
PUBLIC_DIR = ROOT / "public"
logger = logging.getLogger("khoai")


def connect_db() -> sqlite3.Connection:
    return _connect_db(DB_PATH)


@contextmanager
def db_session() -> Iterator[sqlite3.Connection]:
    with _db_session(DB_PATH) as connection:
        yield connection


_retention_service = RetentionService(db_session, BUSINESS_TZ, logger)

def prune_old_logs(retention_days: int | None = None) -> dict[str, int]:
    return _retention_service.prune_old_logs(retention_days)

def prune_evidence_files(evidence_dir: Path | None = None) -> int:
    return _retention_service.prune_evidence_files(evidence_dir)

def _mark_evidence_expired(filename: str) -> int:
    return _retention_service.mark_evidence_expired(filename)

async def _retention_worker() -> None:
    await _retention_service.worker()

# Compatibility rules adapted from KHO.DOAN2; seconds from external camera are demo-scaled.
from .services.external_camera_state import ExternalCameraState

_external_camera_state_store = ExternalCameraState()
# Preserve the historic mutable mapping used by status endpoints and integrations.
_external_camera_state: dict[str, Any] = _external_camera_state_store.data

@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None, None]:
    """Compatibility composition root for application startup and shutdown."""
    def _load_detector():
        # Keep the AI import lazy so API/database-only installations remain usable.
        from ai.person_detector import detector
        return detector

    def _build_telegram_bot():
        from .telegram.integration import build_telegram_bot
        return build_telegram_bot(telegram_backend_services())

    async with application_lifespan(
        app,
        initialize_database=init_db,
        admin_validator=_validate_admin_secret,
        load_detector=_load_detector,
        camera_autostart=CAMERA_AUTOSTART,
        event_sync_worker=_camera_event_sync_worker,
        retention_worker=_retention_worker,
        telegram_bot_factory=_build_telegram_bot,
        logger=logger,
    ):
        yield


VERSION_FILE = ROOT / "VERSION.txt"
try:
    APP_VERSION = VERSION_FILE.read_text(encoding="utf-8").strip() or "0.6.2"
except OSError:
    APP_VERSION = "0.6.2"
OPENAPI_ENABLED = os.getenv("KHOAI_ENABLE_OPENAPI", "0") == "1"
app = FastAPI(
    title="KhoAI – AI warehouse monitoring prototype", version=APP_VERSION, lifespan=lifespan,
    docs_url="/docs" if OPENAPI_ENABLED else None,
    redoc_url="/redoc" if OPENAPI_ENABLED else None,
    openapi_url="/openapi.json" if OPENAPI_ENABLED else None,
)

app.state.webrtc_peers = set()
from .stream_manager import stream_manager
app.state.stream_manager = stream_manager

def init_db() -> None:
    """Initialize the database schema and apply forward-only migrations."""
    from .database import initialize_database
    initialize_database(DB_PATH, now_business, _hash_password)

app.add_middleware(AdminAuditMiddleware)
from .security_headers import SecurityHeadersMiddleware
app.add_middleware(SecurityHeadersMiddleware)

# Authentication and administrator-account endpoints live in a dedicated router.
from types import SimpleNamespace


def telegram_backend_services() -> SimpleNamespace:
    """Build the narrow service bundle consumed by Telegram integration."""
    return SimpleNamespace(
        db_session=db_session,
        BUSINESS_TZ=BUSINESS_TZ,
        now_business=now_business,
        today_business=today_business,
        APP_VERSION=APP_VERSION,
    )


from .routes.auth import AuthRouteServices, create_auth_router
from .routes.history import HistoryRouteServices, create_history_router
from .routes.spatial_mapping import SpatialMappingServices, create_spatial_mapping_router
from .routes.cards import create_cards_router

app.include_router(create_auth_router(cast(AuthRouteServices, SimpleNamespace(
    db_session=db_session, monotonic=time.monotonic, epoch_time=time.time,
    auth_lock=_auth_lock, auth_failures=_auth_failures,
    auth_rate_window=AUTH_RATE_WINDOW, auth_rate_limit=AUTH_RATE_LIMIT,
    dummy_password_hash=_dummy_password_hash, verify_credential_hash=_verify_password,
    record_auth_failure=_record_auth_failure, now_business=now_business,
    hash_credential=_hash_password, session_digest=_session_digest,
    session_seconds=SESSION_SECONDS, load_session=_load_session, require_admin=require_admin,
))))

app.include_router(create_history_router(cast(HistoryRouteServices, SimpleNamespace(
    db_session=db_session,
    business_date=lambda: datetime.now(BUSINESS_TZ).date().isoformat(),
    mask_uid_payload=_mask_uid_payload,
    require_session=require_session,
))))

app.include_router(create_spatial_mapping_router(cast(SpatialMappingServices, SimpleNamespace(
    require_admin=require_admin,
    detector_provider=lambda: __import__("ai.person_detector", fromlist=["detector"]).detector,
    logger=logger,
))))

app.include_router(create_cards_router(SimpleNamespace(
    db_session=db_session, require_admin=require_admin, CardCreate=CardCreate,
    normalize_uid=normalize_uid, now_business=now_business, today_business=today_business,
    detector_provider=lambda: __import__("ai.person_detector", fromlist=["detector"]).detector,
    logger=logger,
)))

from .routes.access import create_access_router, check_access_impl

_access_route_services = SimpleNamespace(
    db_session=db_session, require_admin=require_admin, normalize_uid=normalize_uid,
    now_business=now_business, today_business=today_business, business_tz=BUSINESS_TZ,
    detector_provider=lambda: __import__("ai.person_detector", fromlist=["detector"]).detector,
    logger=logger,
)
app.include_router(create_access_router(_access_route_services))

try:
    RFID_SCAN_DEBOUNCE_SECONDS = min(10.0, max(0.0, float(os.getenv("KHOAI_RFID_SCAN_DEBOUNCE_SECONDS", "1.5"))))
except ValueError:
    RFID_SCAN_DEBOUNCE_SECONDS = 1.5


def _check_rfid_scan(payload: RFIDScan, device_id: str) -> dict[str, Any]:
    return check_access_impl(
        AccessCheck(uid=payload.uid), _access_route_services,
        rfid_device_id=device_id, rfid_debounce_seconds=RFID_SCAN_DEBOUNCE_SECONDS,
    )

from .routes.rfid import create_rfid_router
import importlib

app.include_router(create_rfid_router(SimpleNamespace(
    require_device_key=require_device_key, check_rfid_access=_check_rfid_scan,
    normalize_uid=normalize_uid, db_session=db_session,
    detector_module_provider=lambda: importlib.import_module("ai.person_detector"),
    now_business=now_business, current_alarm_level=lambda: current_alarm_level(),
    incident_status=lambda: _incident_status(), logger=logger,
)))

from .routes.incidents import create_incident_router
from .services.incident_query_service import IncidentQueryService
from .services.incident_alert_commands import IncidentAlertCommandService

_incident_query_service = IncidentQueryService(db_session, _mask_uid_payload)
_incident_alert_command_service = IncidentAlertCommandService(
    db_session=db_session, now_business=now_business,
    current_alarm_level=lambda: current_alarm_level(),
)

app.include_router(create_incident_router(SimpleNamespace(
    db_session=db_session, now_business=now_business,
    require_session=require_session, require_admin=require_admin,
    mask_uid_payload=_mask_uid_payload,
    close_incident_if_resolved=lambda db: _close_incident_if_resolved(db),
    incident_status=lambda: _incident_status(),
    current_alarm_level=lambda: current_alarm_level(),
    acknowledge_all_incidents=lambda: acknowledge_all_incidents(),
    silence_incident_sirens=lambda: silence_incident_sirens(),
    incident_query_service=_incident_query_service,
    acknowledge_alert_command=lambda event_id: _incident_alert_command_service.acknowledge(event_id),
)))

from .routes.devices import create_device_router

app.include_router(create_device_router(SimpleNamespace(
    db_session=db_session, now_business=now_business,
    require_device_key=require_device_key, require_session=require_session,
    current_alarm_level=lambda: current_alarm_level(), incident_status=lambda: _incident_status(),
    mask_uid_payload=_mask_uid_payload, mask_uid=_mask_uid,
)))

from .routes.camera_config import create_camera_config_router

app.include_router(create_camera_config_router(SimpleNamespace(
    require_admin=require_admin,
    detector_provider=lambda: __import__("ai.person_detector", fromlist=["detector"]).detector,
    validate_zone=lambda points: __import__("ai.person_detector", fromlist=["validate_zone"]).validate_zone(points),
    logger=logger,
)))

from .services.camera_access_policy import CameraAccessPolicy

_camera_access_policy = CameraAccessPolicy()

def _ensure_camera_for_read(request: Request, detector: Any) -> None:
    """Compatibility bridge to the extracted camera read-access policy."""
    _camera_access_policy.ensure_camera_for_read(request, detector)

from .routes.camera_status import create_camera_status_router

app.include_router(create_camera_status_router(SimpleNamespace(
    app_version=APP_VERSION, require_session=require_session, now_business=now_business,
    detector_provider=lambda: __import__("ai.person_detector", fromlist=["detector"]).detector,
    augment_detector_status=lambda status: _augment_detector_status(status),
    incident_status=lambda: _incident_status(), logger=logger,
)))

from .routes.camera_media import create_camera_media_router

app.include_router(create_camera_media_router(SimpleNamespace(
    require_admin_query=require_admin_query,
    detector_provider=lambda: __import__("ai.person_detector", fromlist=["detector"]).detector,
    stream_manager_provider=lambda: app.state.stream_manager,
    ensure_camera_for_read=_ensure_camera_for_read,
    evidence_dir_provider=lambda: __import__("ai.person_detector", fromlist=["EVIDENCE_DIR"]).EVIDENCE_DIR,
    logger=logger,
)))

from .routes.camera_events import create_camera_event_router

app.include_router(create_camera_event_router(SimpleNamespace(
    db_session=db_session, require_session=require_session, mask_uid_payload=_mask_uid_payload,
)))

from .routes.telegram_admin import create_telegram_admin_router

app.include_router(create_telegram_admin_router(SimpleNamespace(
    db_session=db_session, require_admin=require_admin, now_business=now_business,
    epoch_time=time.time,
)))

from .routes.system_status import create_system_status_router

_system_status_services = SimpleNamespace(
    db_session=db_session, require_session=require_session, today_business=today_business,
    now_datetime=lambda: datetime.now(BUSINESS_TZ),
    scans_today_allowed=lambda: _scans_today_allowed(),
    detector_provider=lambda: __import__("ai.person_detector", fromlist=["detector"]).detector,
    incident_status=lambda: _incident_status(), current_alarm_level=lambda: current_alarm_level(),
    external_camera_state=lambda: _external_camera_state, logger=logger,
)
app.include_router(create_system_status_router(_system_status_services))

@app.get("/", include_in_schema=False)
def home() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")




app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


# Telegram delivery administration endpoints are registered in routes.telegram_admin.

# Extracted proxy retains background=BackgroundTask(cleanup) and manager.record_bytes("inside", len(chunk)). Compatibility invariants: manager.disconnect("usb", session_id) and manager.disconnect("inside", lifecycle["session_id"]) run in extracted cleanup handlers.
from .routes.camera_streams import create_camera_stream_router


def _create_peer_connection_provider() -> Any:
    """Import the optional WebRTC helper only when its endpoint is used."""
    from .webrtc import create_peer_connection

    return create_peer_connection

_camera_stream_services = SimpleNamespace(
    require_admin_query=require_admin_query, require_admin=require_admin,
    detector_provider=lambda: __import__("ai.person_detector", fromlist=["detector"]).detector,
    ensure_camera_for_read=_ensure_camera_for_read,
    stream_manager_provider=lambda: app.state.stream_manager,
    app_provider=lambda: app,
    session_digest_valid=lambda digest: _session_digest_valid_cached(digest),
    session_digest=_session_digest,
    create_peer_connection_provider=_create_peer_connection_provider,
    environment=lambda key, default="": os.getenv(key, default), logger=logger,
)
_camera_stream_router, _camera_stream_handlers = create_camera_stream_router(_camera_stream_services)
app.include_router(_camera_stream_router)

# Compatibility names retained for existing tests and integrations.
camera_stream = _camera_stream_handlers.camera_stream
camera_webrtc_offer = _camera_stream_handlers.camera_webrtc_offer
camera_streams_websocket = _camera_stream_handlers.camera_streams_websocket
inside_camera_stream = _camera_stream_handlers.inside_camera_stream


INCIDENT_SIREN_SECONDS = max(1, int(os.getenv("KHOAI_SIREN_MAX_SECONDS", "60")))
INCIDENT_EVENT_COOLDOWN_SECONDS = max(0.0, float(os.getenv("KHOAI_INCIDENT_EVENT_COOLDOWN_SECONDS", "3")))


_incident_store: IncidentStore | None = None  # initialized after detector state setup

def _get_incident_store() -> IncidentStore:
    """Return the initialized incident store with an explicit invariant check."""
    if _incident_store is None:
        raise RuntimeError("IncidentStore has not been initialized")
    return _incident_store

def _open_incident(db: sqlite3.Connection, event: dict[str, Any],
                   incident_type: str = "intrusion", *, start_siren: bool = True) -> str:
    return _get_incident_store().open_incident(db, event, incident_type, start_siren=start_siren)

def _record_incident_event(db: sqlite3.Connection, incident_id: str, event: dict[str, Any], source_id: str) -> None:
    _get_incident_store().record_event(db, incident_id, event, source_id)

def _link_event_to_incident(db: sqlite3.Connection, source_id: str, incident_id: str) -> None:
    _get_incident_store().link_event(db, source_id, incident_id)


from .services.detector_state import DetectorStateReader


def _load_detector_for_state():
    # Keep the AI dependency lazy for API/database-only installations.
    from ai.person_detector import detector
    return detector


_detector_state_reader = DetectorStateReader(_load_detector_for_state)


def _current_detector_state() -> str:
    """Compatibility entry point; state normalization lives in DetectorStateReader."""
    _detector_state_reader.detector_provider = _load_detector_for_state
    return _detector_state_reader.get_state()


from .services.incident_store import IncidentStore
from .services.incident_health_policy import IncidentHealthPolicy
_incident_store = IncidentStore(now_business, INCIDENT_EVENT_COOLDOWN_SECONDS,
                                INCIDENT_SIREN_SECONDS, lambda: _current_detector_state())


def _close_incident_if_resolved(db: sqlite3.Connection) -> None:
    _get_incident_store().close_resolved(db)

_incident_health_policy = IncidentHealthPolicy(now_business)

def _health_incident_type(event_type: str | None = None, health_reason: str | None = None) -> str:
    """Compatibility bridge; health classification lives in IncidentHealthPolicy."""
    return _incident_health_policy.incident_type(event_type, health_reason)

def _close_health_incidents(db: sqlite3.Connection, event: dict[str, Any]) -> None:
    """Compatibility bridge; health recovery policy lives in IncidentHealthPolicy."""
    _incident_health_policy.close_recovered(db, event)


from .services.incident_status import IncidentStatusService

_incident_status_service = IncidentStatusService(
    db_session=db_session,
    detector_state=lambda: _current_detector_state(),
)


def _incident_status() -> dict[str, Any]:
    """Compatibility entry point; implementation lives in IncidentStatusService."""
    # Refresh providers to preserve the historic main-module monkeypatch points.
    _incident_status_service.db_session = db_session
    _incident_status_service.detector_state = lambda: _current_detector_state()
    return _incident_status_service.get_status()


def _augment_detector_status(status: dict[str, Any]) -> dict[str, Any]:
    """Compatibility entry point for detector status enrichment."""
    _incident_status_service.db_session = db_session
    _incident_status_service.detector_state = lambda: _current_detector_state()
    return _incident_status_service.augment_detector_status(status)


from .services.camera_event_sync import CameraEventSyncService

_camera_event_sync_service = CameraEventSyncService(
    db_session=db_session,
    now_business=now_business,
    open_incident=_open_incident,
    record_incident_event=_record_incident_event,
    link_event_to_incident=_link_event_to_incident,
    health_incident_type=_health_incident_type,
    close_health_incidents=_close_health_incidents,
    close_incident_if_resolved=_close_incident_if_resolved,
)


def _sync_usb_camera_events(events: list[dict[str, Any]]) -> None:
    """Compatibility entry point; implementation lives in CameraEventSyncService."""
    _camera_event_sync_service.sync_events(events)


from .services.incident_reconciliation import IncidentReconciliationService


def _detector_provider():
    from ai.person_detector import detector
    return detector


_incident_reconciliation_service = IncidentReconciliationService(
    db_session=db_session,
    detector_state=_current_detector_state,
    detector_provider=_detector_provider,
    close_incident_if_resolved=_close_incident_if_resolved,
)


def _reconcile_open_incidents() -> None:
    """Compatibility entry point; reconciliation lives in its own service."""
    _incident_reconciliation_service.db_session = db_session
    _incident_reconciliation_service.detector_state = _current_detector_state
    _incident_reconciliation_service.detector_provider = _detector_provider
    _incident_reconciliation_service.close_incident_if_resolved = _close_incident_if_resolved
    _incident_reconciliation_service.reconcile_open_incidents()


from .services.camera_event_worker import CameraEventSyncWorker

_camera_event_worker = CameraEventSyncWorker(
    detector_provider=_detector_provider,
    sync_events=_sync_usb_camera_events,
    reconcile_incidents=_reconcile_open_incidents,
    logger=logger,
)


async def _camera_event_sync_worker() -> None:
    """Compatibility entry point; polling implementation lives in a service."""
    _camera_event_worker.detector_provider = _detector_provider
    _camera_event_worker.sync_events = _sync_usb_camera_events
    _camera_event_worker.reconcile_incidents = _reconcile_open_incidents
    await _camera_event_worker.run_forever()


# Compatibility entry point retained for integrations that call main.camera_events directly.
def _route_endpoint(router: Any, path: str) -> Any:
    """Find a route endpoint across FastAPI versions with deferred routers."""
    pending: list[Any] = list(router.routes)
    visited: set[int] = set()
    while pending:
        route = pending.pop()
        if id(route) in visited:
            continue
        visited.add(id(route))

        if getattr(route, "path", None) == path:
            endpoint = getattr(route, "endpoint", None)
            if endpoint is not None:
                return endpoint

        original_router = getattr(route, "original_router", None)
        nested_routes = getattr(original_router, "routes", None)
        if nested_routes is not None:
            pending.extend(nested_routes)

    raise LookupError(f"Route endpoint not found: {path}")


def camera_events(request: Request, limit: int = 30) -> list[dict[str, Any]]:
    from .routes.camera_events import create_camera_event_router
    services = SimpleNamespace(db_session=db_session, require_session=require_session,
                               mask_uid_payload=_mask_uid_payload)
    router = create_camera_event_router(services)
    endpoint = _route_endpoint(router, "/api/camera/events")
    return endpoint(request, limit)


# Compatibility service entry point: RFID scan reuses the same access validation logic.
def check_access(payload: AccessCheck) -> dict[str, Any]:
    from .routes.access import check_access_impl
    return check_access_impl(payload, _access_route_services)



# Compatibility entry point retained for integrations that call main.incident_timeline directly.
def incident_timeline(incident_id: str, request: Request) -> dict[str, Any]:
    from .routes.camera_events import create_camera_event_router
    services = SimpleNamespace(db_session=db_session, require_session=require_session,
                               mask_uid_payload=_mask_uid_payload)
    router = create_camera_event_router(services)
    endpoint = _route_endpoint(router, "/api/incidents/{incident_id}/timeline")
    return endpoint(incident_id, request)


from .services.incident_commands import IncidentCommandService

_incident_command_service = IncidentCommandService(
    db_session=db_session,
    now_business=now_business,
    close_incident_if_resolved=_close_incident_if_resolved,
    incident_status=_incident_status,
)


def _refresh_incident_command_dependencies() -> None:
    """Refresh legacy patch points before delegating to the command service."""
    _incident_command_service.db_session = db_session
    _incident_command_service.now_business = now_business
    _incident_command_service.close_incident_if_resolved = _close_incident_if_resolved
    _incident_command_service.incident_status = _incident_status


def acknowledge_all_incidents() -> dict[str, Any]:
    """Compatibility entry point; write-side logic lives in IncidentCommandService."""
    _refresh_incident_command_dependencies()
    return _incident_command_service.acknowledge_all()


def silence_incident_sirens() -> dict[str, Any]:
    """Compatibility entry point; write-side logic lives in IncidentCommandService."""
    _refresh_incident_command_dependencies()
    return _incident_command_service.silence_sirens()


from .services.alarm_level import AlarmLevelResolver

_alarm_level_resolver = AlarmLevelResolver(
    detector_provider=_detector_provider,
    incident_status_provider=_incident_status,
    logger=logger,
)


def current_alarm_level() -> str:
    """Compatibility entry point; alarm-level mapping lives in AlarmLevelResolver."""
    # Refresh providers to preserve historic main-module monkeypatch points.
    _alarm_level_resolver.detector_provider = _detector_provider
    _alarm_level_resolver.incident_status_provider = _incident_status
    return _alarm_level_resolver.get_level()


def integrated_status() -> dict[str, Any]:
    """Compatibility entry point; HTTP route is implemented in routes.system_status."""
    from .routes.system_status import create_system_status_router
    services = SimpleNamespace(
        db_session=db_session, require_session=require_session, today_business=today_business,
        now_datetime=lambda: datetime.now(BUSINESS_TZ),
        scans_today_allowed=lambda: _scans_today_allowed(),
        detector_provider=lambda: __import__("ai.person_detector", fromlist=["detector"]).detector,
        incident_status=lambda: _incident_status(), current_alarm_level=lambda: current_alarm_level(),
        external_camera_state=lambda: _external_camera_state, logger=logger,
    )
    router = create_system_status_router(services)
    endpoint = _route_endpoint(router, "/api/status")
    return endpoint()


from .services.access_statistics import AccessStatisticsService

_access_statistics = AccessStatisticsService(db_session=db_session, business_tz=BUSINESS_TZ)

def _scans_recently_allowed(window_seconds: int = 120) -> int:
    """Compatibility bridge; query implementation lives in AccessStatisticsService."""
    _access_statistics.db_session = db_session
    return _access_statistics.recently_allowed(window_seconds)

def _scans_today_allowed() -> int:
    """Compatibility bridge; query implementation lives in AccessStatisticsService."""
    _access_statistics.db_session = db_session
    return _access_statistics.today_allowed()

from .services.external_alert_store import ExternalAlertStore

_external_alert_store = ExternalAlertStore(db_session=db_session, now_business=now_business)

def _external_alert(level: str, kind: str, zone: str | None, message: str, uid: str | None = None, details: dict[str, Any] | None = None) -> None:
    """Compatibility bridge; deduplication and persistence live in ExternalAlertStore."""
    _external_alert_store.db_session = db_session
    _external_alert_store.now_business = now_business
    _external_alert_store.persist(level, kind, zone, message, uid, details)


from .routes.external_events import create_external_event_router

_external_event_services = SimpleNamespace(
    db_session=db_session, require_admin=require_admin, now_business=now_business,
    scans_recently_allowed=_scans_recently_allowed, external_camera_state=_external_camera_state_store,
    external_time_scale=EXTERNAL_TIME_SCALE, external_warn_minutes=EXTERNAL_WARN_MINUTES,
    external_severe_minutes=EXTERNAL_SEVERE_MINUTES, business_tz=BUSINESS_TZ,
    current_alarm_level=current_alarm_level,
    persist_external_alert=_external_alert,
)
app.include_router(create_external_event_router(_external_event_services))


# Serve the selected KHO.DOAN2 web UI while keeping all API routes above it.
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="selected-web")
