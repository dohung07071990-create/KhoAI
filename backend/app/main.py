"""KhoAI API.

[MODIFIED] Adds card-to-track association, inventory authorization/comparison and persisted alerts.
[MODIFIED] Camera AI remains optional so card/database functions run on low-spec PCs.
"""
from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
import time
import hmac
<<<<<<< HEAD
import asyncio
from contextlib import asynccontextmanager, contextmanager
from datetime import date, datetime, timedelta
=======
from contextlib import asynccontextmanager, contextmanager
from datetime import date, datetime
>>>>>>> 889d624ef29217e05c01da0b46d761ffd4ee4920
from pathlib import Path
from typing import Any, Iterator
from zoneinfo import ZoneInfo

<<<<<<< HEAD
from fastapi import FastAPI, HTTPException, Query, Header, Depends, Request
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator
=======
from fastapi import FastAPI, HTTPException, Query, Header
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
>>>>>>> 889d624ef29217e05c01da0b46d761ffd4ee4920

ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIR = ROOT / "frontend"
PUBLIC_DIR = ROOT / "public"
DB_PATH = Path(os.getenv("DB_PATH", str(ROOT / "data" / "khoai.sqlite3")))
BUSINESS_TZ = ZoneInfo(os.getenv("BUSINESS_TIMEZONE", "Asia/Ho_Chi_Minh"))
UID_RE = re.compile(r"^[0-9A-Fa-f]{4,20}$")
logger = logging.getLogger("khoai")
CAMERA_AUTOSTART = os.getenv("KHOAI_CAMERA_AUTOSTART", "1") != "0"
# Compatibility rules adapted from KHO.DOAN2; seconds from external camera are demo-scaled.
EXTERNAL_TIME_SCALE = int(os.getenv("KHOAI_EXTERNAL_TIME_SCALE", "60"))
EXTERNAL_WARN_MINUTES = int(os.getenv("KHOAI_EXTERNAL_WARN_MINUTES", "10"))
EXTERNAL_SEVERE_MINUTES = int(os.getenv("KHOAI_EXTERNAL_SEVERE_MINUTES", "20"))
_external_camera_state: dict[str, Any] = {"outside": {"people": 0, "max_seconds": 0, "ts": None}, "inside": []}


<<<<<<< HEAD
def prune_old_logs(retention_days: int | None = None) -> dict[str, int]:
    """Delete access/security history older than configured retention; keep current records intact."""
    days = retention_days if retention_days is not None else int(os.getenv("KHOAI_LOG_RETENTION_DAYS", "365"))
    if days <= 0:
        return {"access_logs_deleted": 0, "security_events_deleted": 0}
    cutoff = (datetime.now(BUSINESS_TZ) - timedelta(days=days)).isoformat(timespec="seconds")
    with db_session() as db:
        old_ids = [row[0] for row in db.execute("SELECT id FROM security_events WHERE event_at < ?", (cutoff,)).fetchall()]
        if old_ids:
            db.executemany("DELETE FROM acknowledged_events WHERE event_id=?", [(event_id,) for event_id in old_ids])
        access_deleted = db.execute("DELETE FROM access_logs WHERE event_at < ?", (cutoff,)).rowcount
        events_deleted = db.execute("DELETE FROM security_events WHERE event_at < ?", (cutoff,)).rowcount
    return {"access_logs_deleted": access_deleted, "security_events_deleted": events_deleted}


async def _retention_worker() -> None:
    while True:
        try:
            result = prune_old_logs()
            if result["access_logs_deleted"] or result["security_events_deleted"]:
                logger.info("Đã dọn log cũ: %s", result)
        except Exception:
            logger.exception("Dọn log cũ thất bại")
        await asyncio.sleep(24 * 60 * 60)


=======
>>>>>>> 889d624ef29217e05c01da0b46d761ffd4ee4920
@asynccontextmanager
async def lifespan(_: FastAPI):
    """Khởi tạo khi server chạy: logging -> thư mục dữ liệu + DB -> camera AI (nếu có) ; dọn dẹp khi tắt."""
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    init_db()
    detector = None
    if CAMERA_AUTOSTART:
        try:  # AI là tùy chọn: thiếu opencv/ultralytics thì phần thẻ + CSDL vẫn chạy
            from ai.person_detector import detector
            detector.start()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Camera AI không khởi động được (%s). Cài `pip install -r ai/requirements.txt`.", exc)
            detector = None
<<<<<<< HEAD
    sync_task = asyncio.create_task(_camera_event_sync_worker()) if detector is not None else None
    retention_task = asyncio.create_task(_retention_worker())
    try:
        yield
    finally:
        for task in (sync_task, retention_task):
            if task is not None:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
=======
    try:
        yield
    finally:
>>>>>>> 889d624ef29217e05c01da0b46d761ffd4ee4920
        if detector is not None:
            detector.stop()


<<<<<<< HEAD
OPENAPI_ENABLED = os.getenv("KHOAI_ENABLE_OPENAPI", "0") == "1"
app = FastAPI(
    title="KhoAI – AI warehouse monitoring prototype", version="0.5.4", lifespan=lifespan,
    docs_url="/docs" if OPENAPI_ENABLED else None,
    redoc_url="/redoc" if OPENAPI_ENABLED else None,
    openapi_url="/openapi.json" if OPENAPI_ENABLED else None,
)
=======
app = FastAPI(title="KhoAI – AI warehouse monitoring prototype", version="0.3.0", lifespan=lifespan)
>>>>>>> 889d624ef29217e05c01da0b46d761ffd4ee4920


def connect_db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")  # [NEW] Better local concurrency.
    connection.execute("PRAGMA busy_timeout = 10000")
    return connection


@contextmanager
def db_session() -> Iterator[sqlite3.Connection]:
    connection = connect_db()
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def init_db() -> None:
    """Tạo thư mục dữ liệu, bật WAL và tạo bảng/chỉ mục nếu chưa có (chạy lại nhiều lần vẫn an toàn)."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with db_session() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS cards (
            uid TEXT PRIMARY KEY, name TEXT NOT NULL,
            age INTEGER NOT NULL CHECK (age BETWEEN 0 AND 120),
            active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)), created_at TEXT NOT NULL,
            expires_at TEXT, daily_quota INTEGER NOT NULL DEFAULT 3, used_today INTEGER NOT NULL DEFAULT 0,
            last_reset_date TEXT, color TEXT
        );
        CREATE TABLE IF NOT EXISTS access_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT, uid TEXT NOT NULL, card_name TEXT,
            event_at TEXT NOT NULL, result TEXT NOT NULL CHECK (result IN ('allow', 'deny'))
        );
        CREATE INDEX IF NOT EXISTS idx_access_logs_event_at ON access_logs(event_at DESC);
        CREATE TABLE IF NOT EXISTS inventory (
            sku TEXT PRIMARY KEY, name TEXT NOT NULL,
            registered_quantity INTEGER NOT NULL CHECK (registered_quantity >= 0),
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS security_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT, event_at TEXT NOT NULL,
            event_type TEXT NOT NULL, track_id INTEGER, severity TEXT NOT NULL,
<<<<<<< HEAD
            message TEXT NOT NULL, details_json TEXT NOT NULL DEFAULT '{}', source_event_id TEXT
=======
            message TEXT NOT NULL, details_json TEXT NOT NULL DEFAULT '{}'
>>>>>>> 889d624ef29217e05c01da0b46d761ffd4ee4920
        );
        CREATE INDEX IF NOT EXISTS idx_security_events_at ON security_events(event_at DESC);
        CREATE INDEX IF NOT EXISTS idx_access_logs_uid ON access_logs(uid);
        CREATE TABLE IF NOT EXISTS card_permissions (
            uid TEXT NOT NULL, zone TEXT NOT NULL, PRIMARY KEY(uid, zone)
        );
        CREATE TABLE IF NOT EXISTS pickup_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT, uid TEXT NOT NULL, item TEXT NOT NULL,
            boxes INTEGER NOT NULL DEFAULT 0, zone TEXT, day TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS device_heartbeats (
            device_id TEXT PRIMARY KEY, last_seen TEXT NOT NULL, alarm TEXT NOT NULL DEFAULT 'off'
        );
        CREATE TABLE IF NOT EXISTS acknowledged_events (
            event_id INTEGER PRIMARY KEY, acknowledged_at TEXT NOT NULL
        );
        """)
        # [INTEGRATED] Migrate existing KhoAI databases without deleting existing records.
<<<<<<< HEAD
        event_columns = {row["name"] for row in db.execute("PRAGMA table_info(security_events)").fetchall()}
        if "source_event_id" not in event_columns:
            db.execute("ALTER TABLE security_events ADD COLUMN source_event_id TEXT")
        db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_security_source_event_id ON security_events(source_event_id) WHERE source_event_id IS NOT NULL")
=======
>>>>>>> 889d624ef29217e05c01da0b46d761ffd4ee4920
        existing = {row["name"] for row in db.execute("PRAGMA table_info(cards)").fetchall()}
        for column, declaration in (
            ("expires_at", "TEXT"), ("daily_quota", "INTEGER NOT NULL DEFAULT 3"),
            ("used_today", "INTEGER NOT NULL DEFAULT 0"), ("last_reset_date", "TEXT"), ("color", "TEXT")
        ):
            if column not in existing:
                db.execute(f"ALTER TABLE cards ADD COLUMN {column} {declaration}")


def now_business() -> str:
    return datetime.now(BUSINESS_TZ).isoformat(timespec="seconds")

<<<<<<< HEAD
def today_business() -> str:
    return datetime.now(BUSINESS_TZ).date().isoformat()

def _credential_matches(supplied: str | None, expected: str) -> bool:
    """Compare UTF-8 credentials safely, including non-ASCII input."""
    if supplied is None:
        return False
    try:
        return hmac.compare_digest(supplied.encode("utf-8"), expected.encode("utf-8"))
    except (AttributeError, UnicodeError):
        return False


def require_admin(
    response: Response,
    request: Request,
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
) -> None:
    expected = os.getenv("KHOAI_ADMIN_TOKEN", "").strip()
    if not expected:
        raise HTTPException(status_code=503, detail="Chưa cấu hình KHOAI_ADMIN_TOKEN; API quản trị bị khóa an toàn.")
    if not _credential_matches(x_admin_token, expected):
        raise HTTPException(status_code=401, detail="Thiếu hoặc sai X-Admin-Token.")
    # Browser media elements cannot attach custom headers. Issue a short-lived browser-session cookie
    # so image/stream URLs never need to carry the administrator secret in their query string.
    response.set_cookie(
        key="khoai_admin_session", value=expected, httponly=True, secure=request.url.scheme == "https",
        samesite="strict", path="/", max_age=8 * 60 * 60,
    )


def require_admin_query(
    request: Request,
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
) -> None:
    """Authenticate media using HttpOnly session cookie or explicit admin header.

    Query-string credentials are intentionally unsupported to prevent token leakage
    through browser history, referrers, and HTTP access logs.
    """
    expected = os.getenv("KHOAI_ADMIN_TOKEN", "").strip()
    if not expected:
        raise HTTPException(status_code=503, detail="Chưa cấu hình KHOAI_ADMIN_TOKEN; API đọc bị khóa an toàn.")
    cookie = request.cookies.get("khoai_admin_session")
    if _credential_matches(cookie, expected) or _credential_matches(x_admin_token, expected):
        return
    raise HTTPException(status_code=401, detail="Thiếu hoặc sai phiên quản trị.")


def require_device_key(x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> None:
    expected = os.getenv("KHOAI_API_KEY", "").strip()
    if not expected:
        raise HTTPException(status_code=503, detail="Chưa cấu hình KHOAI_API_KEY; endpoint thiết bị bị khóa.")
    if not _credential_matches(x_api_key, expected):
        raise HTTPException(status_code=401, detail="API key không hợp lệ hoặc chưa được cung cấp.")

=======
>>>>>>> 889d624ef29217e05c01da0b46d761ffd4ee4920

def normalize_uid(uid: str) -> str:
    normalized = re.sub(r"[\s:-]", "", uid).upper()
    if not UID_RE.fullmatch(normalized):
        raise HTTPException(status_code=422, detail="UID phải gồm 4–20 ký tự hex (0–9, A–F).")
    return normalized


class CardCreate(BaseModel):
    uid: str = Field(min_length=4, max_length=24)
    name: str = Field(min_length=1, max_length=100)
    age: int | None = Field(default=None, ge=0, le=120)
    expires_at: str | None = Field(default=None, description="Ngày hết hạn YYYY-MM-DD")
    daily_quota: int = Field(default=3, ge=1, le=1000)
    color: str | None = Field(default=None, max_length=20)
    zones: list[str] = Field(default_factory=list)
    item: str | None = Field(default=None, max_length=100)
    boxes: int = Field(default=0, ge=0, le=100000)

<<<<<<< HEAD
    @field_validator("expires_at")
    @classmethod
    def validate_expiry(cls, value):
        if value in (None, ""):
            return None
        try:
            return date.fromisoformat(value).isoformat()
        except (TypeError, ValueError):
            raise ValueError("expires_at phải đúng định dạng YYYY-MM-DD")

    @field_validator("color")
    @classmethod
    def validate_color(cls, value):
        if value in (None, ""):
            return None
        if not re.fullmatch(r"#[0-9A-Fa-f]{6}|[A-Za-z]{1,20}", value):
            raise ValueError("color chỉ nhận mã hex #RRGGBB hoặc tên màu chữ")
        return value

=======
>>>>>>> 889d624ef29217e05c01da0b46d761ffd4ee4920

class RFIDScan(BaseModel):
    uid: str = Field(min_length=4, max_length=24)
    device_id: str = Field(default="esp32-door", max_length=100)


class DeviceHeartbeat(BaseModel):
    device_id: str = Field(default="esp32-door", max_length=100)


class SecurityEventInput(BaseModel):
    camera: str = Field(default="external", max_length=40)
    people_in_zone: int = Field(default=0, ge=0)
    max_seconds: float = Field(default=0, ge=0)
    people: list[dict[str, Any]] = Field(default_factory=list)
    boxes: int = Field(default=0, ge=0)
    event_type: str | None = None
    severity: str = Field(default="warning", max_length=20)
    message: str | None = Field(default=None, max_length=500)
    details: dict[str, Any] = Field(default_factory=dict)


class AccessCheck(BaseModel):
    uid: str = Field(min_length=4, max_length=24)
    # [NEW] Optional track ID must be explicitly selected; RFID alone cannot identify a person in video.
    track_id: int | None = Field(default=None, ge=0)


class CameraZoneUpdate(BaseModel):
    points: list[list[float]] = Field(min_length=3, max_length=30)
    frame_size: list[int] | None = Field(default=None, min_length=2, max_length=2)


<<<<<<< HEAD
class CameraAntiTheftUpdate(BaseModel):
    enabled: bool
=======
class CameraSourceUpdate(BaseModel):
    source: str = Field(default="auto", max_length=300, description="'auto', index (0,1,2...), URL hoặc đường dẫn thiết bị")
>>>>>>> 889d624ef29217e05c01da0b46d761ffd4ee4920


class TrackAssociation(BaseModel):
    uid: str = Field(min_length=4, max_length=24)
    track_id: int = Field(ge=0)


<<<<<<< HEAD
=======
class InventoryItem(BaseModel):
    sku: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=100)
    registered_quantity: int = Field(ge=0, le=100000)


class InventoryCompare(BaseModel):
    sku: str = Field(min_length=1, max_length=50)
    observed_quantity: int = Field(ge=0, le=100000)
    # Optional tracking ID for audit context, not proof of identity.
    track_id: int | None = Field(default=None, ge=0)


>>>>>>> 889d624ef29217e05c01da0b46d761ffd4ee4920
@app.get("/", include_in_schema=False)
def home() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")


<<<<<<< HEAD
=======
@app.get("/manus-routes.json", include_in_schema=False)
def route_manifest() -> FileResponse:
    return FileResponse(PUBLIC_DIR / "manus-routes.json", media_type="application/json")
>>>>>>> 889d624ef29217e05c01da0b46d761ffd4ee4920


app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


@app.get("/api/health")
def health() -> dict[str, str]:
<<<<<<< HEAD
    return {"status": "ok", "service": "kho-ai-demo", "version": "0.5.4"}


@app.get("/api/camera/status", dependencies=[Depends(require_admin)])
=======
    return {"status": "ok", "service": "kho-ai-demo", "version": "0.3.0"}


@app.get("/api/camera/status")
>>>>>>> 889d624ef29217e05c01da0b46d761ffd4ee4920
def camera_status() -> dict[str, Any]:
    """Tình trạng camera USB và pipeline YOLO/ByteTrack."""
    try:
        from ai.person_detector import detector
        return detector.status()
    except Exception as exc:  # noqa: BLE001
        logger.exception("Không đọc được trạng thái camera AI")
        raise HTTPException(status_code=503, detail=f"Không đọc được trạng thái camera: {exc}") from exc


<<<<<<< HEAD
@app.get("/api/camera/stream", dependencies=[Depends(require_admin_query)])
=======
@app.get("/api/camera/stream")
>>>>>>> 889d624ef29217e05c01da0b46d761ffd4ee4920
def camera_stream() -> StreamingResponse:
    """Phát video MJPEG đã được YOLO vẽ khung nhận diện từ camera USB."""
    try:
        from ai.person_detector import detector
        detector.start()
    except Exception as exc:  # noqa: BLE001
        logger.exception("Không thể khởi động luồng camera")
        raise HTTPException(status_code=503, detail=f"Không thể khởi động camera AI: {exc}") from exc

<<<<<<< HEAD
    async def frames():
        last_seq = 0
        try:
            while True:
                # Wait off the event loop; disconnect cancellation no longer occupies a sync threadpool worker.
                result = await asyncio.to_thread(detector.wait_for_frame, last_seq, timeout=2.0)
                if result is None:
                    continue
                last_seq, jpeg = result
                yield b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: " + str(len(jpeg)).encode("ascii") + b"\r\n\r\n" + jpeg + b"\r\n"
        except asyncio.CancelledError:
            raise
=======
    def frames():
        last_seq = 0
        while True:
            result = detector.wait_for_frame(last_seq, timeout=2.0)
            if result is None:
                # Keep connection alive while camera/model is warming up or reconnecting.
                continue
            last_seq, jpeg = result
            yield b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: " + str(len(jpeg)).encode("ascii") + b"\r\n\r\n" + jpeg + b"\r\n"
>>>>>>> 889d624ef29217e05c01da0b46d761ffd4ee4920

    return StreamingResponse(frames(), media_type="multipart/x-mixed-replace; boundary=frame", headers={"Cache-Control": "no-cache, no-store, must-revalidate", "Pragma": "no-cache", "X-Accel-Buffering": "no"})


<<<<<<< HEAD
@app.put("/api/camera/anti-theft", dependencies=[Depends(require_admin)])
def update_camera_anti_theft(payload: CameraAntiTheftUpdate) -> dict[str, Any]:
    """Bật/tắt độc lập; khi bật, người đang ở trong vùng nguy hiểm được đánh giá ngay."""
    try:
        from ai.person_detector import detector
        detector.start()
        return {"ok": True, **detector.set_anti_theft(payload.enabled)}
    except Exception as exc:  # noqa: BLE001
        logger.exception("Không thể thay đổi trạng thái chống trộm")
        raise HTTPException(status_code=503, detail=f"Không thể thay đổi chống trộm: {exc}") from exc


@app.get("/api/camera/zone", dependencies=[Depends(require_admin)])
=======
@app.get("/api/camera/zone")
>>>>>>> 889d624ef29217e05c01da0b46d761ffd4ee4920
def get_camera_zone() -> dict[str, Any]:
    """Đọc vùng bảo vệ của riêng camera USB ngoài."""
    try:
        from ai.person_detector import detector
        status = detector.status()
        return {"points": status["zone_points"], "frame_size": status["zone_frame_size"],
                "zone_mode": status["zone_mode"]}
    except Exception as exc:  # noqa: BLE001
        logger.exception("Không đọc được vùng bảo vệ camera USB")
        raise HTTPException(status_code=503, detail=f"Không đọc được vùng bảo vệ: {exc}") from exc


<<<<<<< HEAD
@app.put("/api/camera/zone", dependencies=[Depends(require_admin)])
=======
@app.put("/api/camera/zone")
>>>>>>> 889d624ef29217e05c01da0b46d761ffd4ee4920
def update_camera_zone(payload: CameraZoneUpdate) -> dict[str, Any]:
    """Lưu vùng bảo vệ chuẩn hóa (0–1) cho pipeline camera USB + YOLO."""
    try:
        from ai.person_detector import detector, validate_zone
        points = [(float(p[0]), float(p[1])) for p in payload.points if len(p) == 2]
        if len(points) != len(payload.points):
            raise ValueError("Mỗi điểm vùng phải có đúng hai tọa độ x, y.")
        validate_zone(points)
        current = detector.status().get("frame_size")
        requested_size = payload.frame_size or current
        frame_size = (int(requested_size[0]), int(requested_size[1])) if requested_size else None
        detector.set_zone(points, save=True, frame_size=frame_size)
        return {"ok": True, **get_camera_zone()}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("Không thể cập nhật vùng bảo vệ camera USB")
        raise HTTPException(status_code=503, detail=f"Không thể cập nhật vùng bảo vệ: {exc}") from exc


<<<<<<< HEAD
@app.get("/api/camera/heatmap", dependencies=[Depends(require_admin_query)])
=======
@app.get("/api/camera/heatmap")
>>>>>>> 889d624ef29217e05c01da0b46d761ffd4ee4920
def camera_heatmap() -> Response:
    """Ảnh nhiệt mật độ xuất hiện người, chỉ dựa trên camera USB ngoài."""
    try:
        from ai.person_detector import detector
        detector.start()
        jpeg = detector.heatmap_jpeg()
        if jpeg is None:
            raise HTTPException(status_code=503, detail="Camera chưa có khung hình; hãy chờ vài giây.")
        return Response(content=jpeg, media_type="image/jpeg", headers={"Cache-Control": "no-store"})
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("Không tạo được heatmap camera USB")
        raise HTTPException(status_code=503, detail=f"Không tạo được heatmap camera: {exc}") from exc


<<<<<<< HEAD
@app.get("/api/camera/evidence/{filename}", dependencies=[Depends(require_admin_query)])
=======
@app.get("/api/camera/evidence/{filename}")
>>>>>>> 889d624ef29217e05c01da0b46d761ffd4ee4920
def camera_evidence(filename: str) -> FileResponse:
    """Phục vụ ảnh bằng chứng do camera USB tạo; chỉ chấp nhận tên JPEG UUID."""
    if not re.fullmatch(r"[0-9a-f]{32}\.jpg", filename):
        raise HTTPException(status_code=404, detail="Không tìm thấy ảnh bằng chứng.")
    try:
        from ai.person_detector import EVIDENCE_DIR
        path = EVIDENCE_DIR / filename
        if not path.is_file():
            raise HTTPException(status_code=404, detail="Ảnh bằng chứng không tồn tại hoặc đã bị xóa.")
        return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "no-store"})
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("Không đọc được ảnh bằng chứng camera USB")
        raise HTTPException(status_code=503, detail=f"Không đọc được ảnh bằng chứng: {exc}") from exc


<<<<<<< HEAD
@app.get("/api/camera/snapshot", dependencies=[Depends(require_admin_query)])
=======
@app.get("/api/camera/snapshot")
>>>>>>> 889d624ef29217e05c01da0b46d761ffd4ee4920
def camera_snapshot() -> Response:
    """Ảnh JPEG mới nhất từ webcam USB, không vẽ overlay AI; dùng kiểm tra/căn chỉnh."""
    try:
        from ai.person_detector import detector
        detector.start()
        jpeg = detector.snapshot_jpeg(annotated=False)
        if jpeg is None:
            raise HTTPException(status_code=503, detail="Camera chưa có khung hình; hãy chờ vài giây.")
        return Response(content=jpeg, media_type="image/jpeg", headers={"Cache-Control": "no-store"})
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("Không chụp được ảnh camera USB")
        raise HTTPException(status_code=503, detail=f"Không chụp được ảnh camera: {exc}") from exc


def _sync_usb_camera_events(events: list[dict[str, Any]]) -> None:
<<<<<<< HEAD
    """Persist detector events asynchronously; source_event_id makes insertion idempotent."""
    if not events:
        return
    with db_session() as db:
        for event in events:
            source_time = str(event.get("event_at") or "")
            if not source_time:
                continue
            event_type = str(event.get("type") or "camera_event")
            severity_raw = str(event.get("severity", "medium")).lower()
            severity = "severe" if severity_raw in {"high", "critical", "severe"} else "warning" if severity_raw in {"medium", "warning"} else "info"
            source_id = str(event.get("event_id") or f"{event_type}:{event.get('track_id')}:{source_time}")
            details = {"source": "usb_external", "camera_event_at": source_time, "track_id": event.get("track_id"), "zone": "external", **event}
            existing = db.execute("SELECT id, details_json FROM security_events WHERE source_event_id=?", (source_id,)).fetchone()
            details_json = json.dumps(details, ensure_ascii=False)
            if existing:
                # Evidence metadata may be attached shortly after the detector first emits the event.
                if event.get("evidence_url") and not json.loads(existing["details_json"] or "{}").get("evidence_url"):
                    db.execute("UPDATE security_events SET details_json=? WHERE id=?", (details_json, existing["id"]))
            else:
                db.execute("""INSERT INTO security_events(event_at,event_type,track_id,severity,message,details_json,source_event_id)
                    VALUES(?,?,?,?,?,?,?)""", (source_time, event_type, event.get("track_id"), severity,
                    str(event.get("message") or "Sự kiện camera USB ngoài."), details_json, source_id))


async def _camera_event_sync_worker() -> None:
    while True:
        try:
            from ai.person_detector import detector
            _sync_usb_camera_events(detector.get_events(100))
        except Exception:
            logger.exception("Đồng bộ sự kiện camera USB thất bại")
        await asyncio.sleep(2.0)


@app.get("/api/camera/events", dependencies=[Depends(require_admin)])
def camera_events(limit: int = Query(default=30, ge=1, le=100)) -> list[dict[str, Any]]:
    """Read-only lịch sử sự kiện đã được worker nền đồng bộ vào SQLite."""
    with db_session() as db:
        rows = db.execute("SELECT event_at,event_type,track_id,severity,message,details_json FROM security_events WHERE source_event_id IS NOT NULL ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    result = []
    for row in rows:
        details = json.loads(row["details_json"] or "{}")
        result.append({**details, "type": row["event_type"], "event_at": row["event_at"], "track_id": row["track_id"], "severity": row["severity"], "message": row["message"]})
    return result


@app.get("/api/cards", dependencies=[Depends(require_admin)])
=======
    """Đưa sự kiện từ worker USB vào bảng cảnh báo KhoAI, không ghi lặp khi UI poll."""
    if not events:
        return
    with db_session() as db:
        for event in reversed(events):
            source_time = str(event.get("event_at") or "")
            event_type = str(event.get("type") or "camera_event")
            track_id = event.get("track_id")
            if not source_time:
                continue
            # Vào/ra vùng bình thường vẫn nằm trong lịch sử camera, nhưng không biến
            # thành cảnh báo đỏ/vàng toàn hệ thống nếu không có rủi ro thực tế.
            if event_type in {"zone_entry", "zone_exit"} and str(event.get("severity", "low")).lower() in {"low", "info", "informational"}:
                continue
            marker = f'"camera_event_at": "{source_time}"'
            exists = db.execute(
                "SELECT id FROM security_events WHERE event_type=? AND track_id IS ? AND details_json LIKE ? LIMIT 1",
                (event_type, track_id, f"%{marker}%"),
            ).fetchone()
            if exists:
                continue
            original_severity = str(event.get("severity", "medium")).lower()
            severity = "severe" if original_severity in {"high", "critical", "severe"} else "warning"
            details = {"source": "usb_external", "camera_event_at": source_time,
                       "track_id": track_id, "zone": "external", **event}
            db.execute(
                "INSERT INTO security_events(event_at,event_type,track_id,severity,message,details_json) VALUES(?,?,?,?,?,?)",
                (source_time, event_type, track_id, severity,
                 str(event.get("message") or "Sự kiện camera USB ngoài."), json.dumps(details, ensure_ascii=False)),
            )


@app.get("/api/camera/events")
def camera_events(limit: int = Query(default=30, ge=1, le=100)) -> list[dict[str, Any]]:
    """Lịch sử sự kiện riêng của camera USB; đồng bộ vào bảng cảnh báo hiện có của KhoAI."""
    try:
        from ai.person_detector import detector
        events = detector.get_events(limit)
        _sync_usb_camera_events(events)
        return events
    except Exception as exc:  # noqa: BLE001
        logger.exception("Không đọc được sự kiện camera USB")
        raise HTTPException(status_code=503, detail=f"Không đọc được sự kiện camera: {exc}") from exc


@app.get("/api/cards")
>>>>>>> 889d624ef29217e05c01da0b46d761ffd4ee4920
def list_cards() -> list[dict[str, Any]]:
    with db_session() as db:
        rows = db.execute("SELECT uid, name, age, active, created_at, expires_at, daily_quota, used_today, color FROM cards ORDER BY created_at DESC").fetchall()
        cards = []
        for row in rows:
            item = dict(row)
            item["zones"] = [r["zone"] for r in db.execute("SELECT zone FROM card_permissions WHERE uid=? ORDER BY zone", (item["uid"],)).fetchall()]
            order = db.execute("SELECT item, boxes FROM pickup_orders WHERE uid=? ORDER BY id DESC LIMIT 1", (item["uid"],)).fetchone()
            item["item"] = order["item"] if order else None
            item["boxes"] = order["boxes"] if order else 0
            cards.append(item)
    return cards


<<<<<<< HEAD
@app.post("/api/cards", status_code=201, dependencies=[Depends(require_admin)])
=======
@app.post("/api/cards", status_code=201)
>>>>>>> 889d624ef29217e05c01da0b46d761ffd4ee4920
def create_card(payload: CardCreate) -> dict[str, Any]:
    uid, name, created_at = normalize_uid(payload.uid), payload.name.strip(), now_business()
    if not name:
        raise HTTPException(status_code=422, detail="Tên người không được để trống.")
    try:
        with db_session() as db:
            db.execute("""INSERT INTO cards(uid, name, age, active, created_at, expires_at, daily_quota,
                       used_today, last_reset_date, color) VALUES (?, ?, ?, 1, ?, ?, ?, 0, ?, ?)""",
                       (uid, name, payload.age if payload.age is not None else 0, created_at, payload.expires_at, payload.daily_quota,
<<<<<<< HEAD
                        today_business(), payload.color))
=======
                        date.today().isoformat(), payload.color))
>>>>>>> 889d624ef29217e05c01da0b46d761ffd4ee4920
            db.execute("DELETE FROM card_permissions WHERE uid = ?", (uid,))
            for zone in payload.zones:
                if zone not in {"entry", "exit", "important", "critical"}:
                    raise HTTPException(status_code=422, detail=f"Vùng không hợp lệ: {zone}")
                db.execute("INSERT INTO card_permissions(uid, zone) VALUES (?, ?)", (uid, zone))
            if payload.item and payload.boxes:
                db.execute("INSERT INTO pickup_orders(uid,item,boxes,zone,day) VALUES(?,?,?,?,?)",
                           (uid, payload.item.strip(), payload.boxes, payload.zones[0] if payload.zones else None,
<<<<<<< HEAD
                            today_business()))
=======
                            date.today().isoformat()))
>>>>>>> 889d624ef29217e05c01da0b46d761ffd4ee4920
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=409, detail="UID này đã được cấp thẻ.") from exc
    return {"uid": uid, "name": name, "age": payload.age if payload.age is not None else 0, "active": True, "created_at": created_at,
            "expires_at": payload.expires_at, "daily_quota": payload.daily_quota,
            "color": payload.color, "zones": payload.zones, "item": payload.item, "boxes": payload.boxes}


<<<<<<< HEAD
@app.post("/api/access/check", dependencies=[Depends(require_admin)])
def check_access(payload: AccessCheck) -> dict[str, Any]:
    uid = normalize_uid(payload.uid)
    with db_session() as db:
        db.execute("BEGIN IMMEDIATE")
        card = db.execute("SELECT * FROM cards WHERE uid = ?", (uid,)).fetchone()
        name, reason = (card["name"], None) if card else (None, "unknown_card")
        today = today_business()
        if card:
            if not card["active"]:
                reason = "inactive_card"
            if reason is None and card["expires_at"]:
                try:
                    expiry = date.fromisoformat(card["expires_at"])
                except ValueError:
                    reason = "invalid_expiry"
                else:
                    if expiry < date.fromisoformat(today):
                        reason = "expired"
            if reason is None:
                # BEGIN IMMEDIATE serializes competing scans; quota consumption is one conditional UPDATE.
                db.execute("UPDATE cards SET used_today=0,last_reset_date=? WHERE uid=? AND (last_reset_date IS NULL OR last_reset_date<>?)", (today, uid, today))
                changed = db.execute("UPDATE cards SET used_today=used_today+1 WHERE uid=? AND active=1 AND used_today<daily_quota", (uid,)).rowcount
                if changed != 1:
                    reason = "quota_exhausted"
=======
@app.post("/api/access/check")
def check_access(payload: AccessCheck) -> dict[str, Any]:
    uid = normalize_uid(payload.uid)
    with db_session() as db:
        card = db.execute("SELECT * FROM cards WHERE uid = ?", (uid,)).fetchone()
        name, reason = (card["name"], None) if card else (None, "unknown_card")
        today = date.today().isoformat()
        if card:
            if not card["active"]:
                reason = "inactive_card"
            elif card["last_reset_date"] != today:
                db.execute("UPDATE cards SET used_today=0,last_reset_date=? WHERE uid=?", (today, uid))
            if reason is None and card["expires_at"] and card["expires_at"] < today:
                reason = "expired"
            if reason is None:
                fresh = db.execute("SELECT used_today,daily_quota FROM cards WHERE uid=?", (uid,)).fetchone()
                if fresh["used_today"] >= fresh["daily_quota"]:
                    reason = "quota_exhausted"
            if reason is None:
                db.execute("UPDATE cards SET used_today=used_today+1 WHERE uid=?", (uid,))
>>>>>>> 889d624ef29217e05c01da0b46d761ffd4ee4920
        allowed = reason is None
        result = "allow" if allowed else "deny"
        db.execute("INSERT INTO access_logs(uid, card_name, event_at, result) VALUES (?, ?, ?, ?)",
                   (uid, name, now_business(), result))
        if reason:
            db.execute("""INSERT INTO security_events(event_at,event_type,track_id,severity,message,details_json)
                          VALUES(?, ?, ?, ?, ?, ?)""",
                       (now_business(), "rfid_denied", payload.track_id, "warning",
                        f"Quẹt thẻ bị từ chối ({reason}): {name or uid}",
                        json.dumps({"uid": uid, "reason": reason}, ensure_ascii=False)))
    associated = None
    # [NEW] Only associate when caller supplies the visible track ID explicitly.
    if allowed and payload.track_id is not None:
        try:
            from ai.person_detector import detector
            associated = detector.associate_card(payload.track_id, uid, name)
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"Không thể liên kết thẻ với camera: {exc}") from exc
    return {"uid": uid, "allowed": allowed, "result": result,
            "message": "cho phép" if allowed else "từ chối", "reason": reason, "name": name,
            "track_association": associated,
            "note": "Quẹt thẻ không tự xác định được ID người trên camera; cần truyền track_id nếu muốn liên kết."}


<<<<<<< HEAD
@app.post("/api/access/associate", dependencies=[Depends(require_admin)])
def associate_access_track(payload: TrackAssociation) -> dict[str, Any]:
    """Operator explicitly links a recently scanned valid UID to a visible USB-camera track ID."""
    uid = normalize_uid(payload.uid)
    cutoff = (datetime.now(BUSINESS_TZ) - timedelta(minutes=2)).isoformat(timespec="seconds")
    with db_session() as db:
        card = db.execute("SELECT uid,name,active FROM cards WHERE uid=?", (uid,)).fetchone()
        recent_scan = db.execute("SELECT id FROM access_logs WHERE uid=? AND result='allow' AND event_at>=? ORDER BY id DESC LIMIT 1", (uid, cutoff)).fetchone()
    if not card or not card["active"] or not recent_scan:
        raise HTTPException(status_code=409, detail="Chỉ liên kết được thẻ đang hoạt động vừa được xác thực thành công trong 2 phút gần nhất.")
    try:
        from ai.person_detector import detector
        detector.start()
        status = detector.status()
        if payload.track_id not in status.get("tracked_person_ids", []):
            raise HTTPException(status_code=409, detail="Track ID không còn xuất hiện trong camera USB. Hãy chọn ID đang hiển thị.")
        association = detector.associate_card(payload.track_id, uid, card["name"])
        return {"ok": True, **association}
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Không thể liên kết thẻ với Track ID")
        raise HTTPException(status_code=503, detail=f"Không thể liên kết thẻ với camera: {exc}") from exc


@app.get("/api/logs", dependencies=[Depends(require_admin)])
=======
@app.get("/api/logs")
>>>>>>> 889d624ef29217e05c01da0b46d761ffd4ee4920
def list_logs(limit: int = Query(default=100, ge=1, le=500)) -> list[dict[str, Any]]:
    with db_session() as db:
        rows = db.execute("SELECT id, uid, card_name, event_at, result FROM access_logs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return [dict(row) for row in rows]


<<<<<<< HEAD
@app.get("/api/stats", dependencies=[Depends(require_admin)])
=======
@app.get("/api/stats")
>>>>>>> 889d624ef29217e05c01da0b46d761ffd4ee4920
def stats() -> dict[str, int]:
    today = datetime.now(BUSINESS_TZ).date().isoformat()
    with db_session() as db:
        cards = db.execute("SELECT COUNT(*) FROM cards WHERE active = 1").fetchone()[0]
        scans = db.execute("SELECT COUNT(*) FROM access_logs WHERE substr(event_at, 1, 10) = ?", (today,)).fetchone()[0]
        denied = db.execute("SELECT COUNT(*) FROM access_logs WHERE substr(event_at, 1, 10) = ? AND result = 'deny'", (today,)).fetchone()[0]
<<<<<<< HEAD
        alerts = db.execute("SELECT COUNT(*) FROM security_events WHERE substr(event_at, 1, 10) = ? AND severity IN ('warning','severe')", (today,)).fetchone()[0]
=======
        alerts = db.execute("SELECT COUNT(*) FROM security_events WHERE substr(event_at, 1, 10) = ?", (today,)).fetchone()[0]
>>>>>>> 889d624ef29217e05c01da0b46d761ffd4ee4920
    return {"active_cards": cards, "scans_today": scans, "denied_today": denied, "alerts_today": alerts}



# [INTEGRATED] Compatibility endpoints from KHO.DOAN2; the KhoAI database remains authoritative.
@app.post("/api/rfid/scan")
<<<<<<< HEAD
def rfid_scan(payload: RFIDScan, _: None = Depends(require_device_key)) -> dict[str, Any]:
=======
def rfid_scan(payload: RFIDScan, x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> dict[str, Any]:
    configured_key = os.getenv("KHOAI_API_KEY", "").strip()
    if configured_key and (not x_api_key or not hmac.compare_digest(x_api_key, configured_key)):
        raise HTTPException(status_code=401, detail="API key không hợp lệ hoặc chưa được cung cấp.")
>>>>>>> 889d624ef29217e05c01da0b46d761ffd4ee4920
    result = check_access(AccessCheck(uid=payload.uid))
    return {"allow": result["allowed"], "reason": result.get("reason"),
            "name": result.get("name"), "alarm": current_alarm_level()}


def current_alarm_level() -> str:
    with db_session() as db:
        levels = {row["severity"] for row in db.execute(
             "SELECT severity FROM security_events WHERE severity IN ('warning','severe') AND id NOT IN (SELECT event_id FROM acknowledged_events)"
        ).fetchall()}
    return "severe" if "severe" in levels else "warning" if levels else "off"


<<<<<<< HEAD
@app.post("/api/device/heartbeat", dependencies=[Depends(require_device_key)])
=======
@app.post("/api/device/heartbeat")
>>>>>>> 889d624ef29217e05c01da0b46d761ffd4ee4920
def device_heartbeat(payload: DeviceHeartbeat) -> dict[str, str]:
    with db_session() as db:
        db.execute("""INSERT INTO device_heartbeats(device_id,last_seen,alarm) VALUES(?,?,?)
                      ON CONFLICT(device_id) DO UPDATE SET last_seen=excluded.last_seen,alarm=excluded.alarm""",
                   (payload.device_id, now_business(), current_alarm_level()))
    return {"alarm": current_alarm_level()}


<<<<<<< HEAD
@app.get("/api/alerts", dependencies=[Depends(require_admin)])
def list_alerts(
    limit: int = Query(default=100, ge=1, le=500),
    severity: str = Query(default="alerts", pattern="^(alerts|info|all|warning|severe)$"),
) -> list[dict[str, Any]]:
    severity_sql = {
        "alerts": "e.severity IN ('warning','severe')",
        "info": "e.severity='info'",
        "warning": "e.severity='warning'",
        "severe": "e.severity='severe'",
        "all": "1=1",
    }[severity]
    with db_session() as db:
        rows = db.execute(f"""SELECT e.*, CASE WHEN a.event_id IS NULL THEN 0 ELSE 1 END AS handled
            FROM security_events e LEFT JOIN acknowledged_events a ON a.event_id=e.id
            WHERE {severity_sql} ORDER BY e.id DESC LIMIT ?""", (limit,)).fetchall()
=======
@app.get("/api/alerts")
def list_alerts(limit: int = Query(default=100, ge=1, le=500)) -> list[dict[str, Any]]:
    with db_session() as db:
        rows = db.execute("""SELECT e.*, CASE WHEN a.event_id IS NULL THEN 0 ELSE 1 END AS handled
            FROM security_events e LEFT JOIN acknowledged_events a ON a.event_id=e.id
            ORDER BY e.id DESC LIMIT ?""", (limit,)).fetchall()
>>>>>>> 889d624ef29217e05c01da0b46d761ffd4ee4920
    result = []
    for row in rows:
        item = dict(row)
        try:
            item["details"] = json.loads(item.pop("details_json"))
        except (ValueError, TypeError):
            item["details"] = {}
        # Compatibility aliases for the selected KHO.DOAN2 web UI.
        details = item.get("details") or {}
        item.setdefault("level", item.get("severity", "warning"))
        item.setdefault("kind", item.get("event_type", "camera_event"))
        item.setdefault("ts", item.get("event_at"))
        item.setdefault("zone", details.get("zone"))
        item.setdefault("uid", details.get("uid"))
        result.append(item)
    return result


<<<<<<< HEAD
@app.get("/api/scans", dependencies=[Depends(require_admin)])
=======
@app.get("/api/scans")
>>>>>>> 889d624ef29217e05c01da0b46d761ffd4ee4920
def list_scans_compat(limit: int = Query(default=100, ge=1, le=500)) -> list[dict[str, Any]]:
    """Compatibility response for the selected KHO.DOAN2 web UI."""
    with db_session() as db:
        rows = db.execute("SELECT id, uid, card_name, event_at, result FROM access_logs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        records = []
        for row in rows:
            item = dict(row)
            item["ts"] = item.pop("event_at")
            item["name"] = item.pop("card_name")
            item["reason"] = None
            if item["result"] == "deny":
                denied = db.execute("SELECT details_json FROM security_events WHERE event_type='rfid_denied' AND details_json LIKE ? ORDER BY id DESC LIMIT 1", (f'%"uid": "{item["uid"]}"%',)).fetchone()
                if denied:
                    try:
                        item["reason"] = json.loads(denied["details_json"]).get("reason")
                    except (ValueError, TypeError):
                        pass
            records.append(item)
    return records


<<<<<<< HEAD
@app.delete("/api/cards/{uid}", dependencies=[Depends(require_admin)])
=======
@app.delete("/api/cards/{uid}")
>>>>>>> 889d624ef29217e05c01da0b46d761ffd4ee4920
def delete_card_compat(uid: str) -> dict[str, Any]:
    """Delete a card from the selected web UI without deleting historical access/security logs."""
    normalized = normalize_uid(uid)
    with db_session() as db:
        exists = db.execute("SELECT uid FROM cards WHERE uid=?", (normalized,)).fetchone()
        if not exists:
            raise HTTPException(status_code=404, detail="Không tìm thấy thẻ.")
        db.execute("DELETE FROM card_permissions WHERE uid=?", (normalized,))
        db.execute("DELETE FROM pickup_orders WHERE uid=?", (normalized,))
        db.execute("DELETE FROM cards WHERE uid=?", (normalized,))
    return {"ok": True}


<<<<<<< HEAD
@app.post("/api/alerts/{event_id}/ack", dependencies=[Depends(require_admin)])
=======
@app.post("/api/alerts/{event_id}/ack")
>>>>>>> 889d624ef29217e05c01da0b46d761ffd4ee4920
def acknowledge_alert(event_id: int) -> dict[str, Any]:
    with db_session() as db:
        exists = db.execute("SELECT id FROM security_events WHERE id=?", (event_id,)).fetchone()
        if not exists:
            raise HTTPException(status_code=404, detail="Không tìm thấy cảnh báo.")
        db.execute("INSERT OR IGNORE INTO acknowledged_events(event_id,acknowledged_at) VALUES(?,?)",
                   (event_id, now_business()))
    return {"ok": True, "alarm": current_alarm_level()}


<<<<<<< HEAD
@app.get("/api/rfid/last-unknown", dependencies=[Depends(require_admin)])
=======
@app.get("/api/rfid/last-unknown")
>>>>>>> 889d624ef29217e05c01da0b46d761ffd4ee4920
def last_unknown_card() -> dict[str, Any]:
    with db_session() as db:
        row = db.execute("SELECT uid,event_at FROM access_logs WHERE result='deny' ORDER BY id DESC").fetchone()
    return {"uid": row["uid"] if row else None, "ts": row["event_at"] if row else None}


<<<<<<< HEAD
@app.get("/api/status", dependencies=[Depends(require_admin)])
def integrated_status() -> dict[str, Any]:
    today = today_business()
=======
@app.get("/api/status")
def integrated_status() -> dict[str, Any]:
    today = date.today().isoformat()
>>>>>>> 889d624ef29217e05c01da0b46d761ffd4ee4920
    with db_session() as db:
        card_count = db.execute("SELECT COUNT(*) FROM cards").fetchone()[0]
        scan_count = db.execute("SELECT COUNT(*) FROM access_logs WHERE substr(event_at,1,10)=?", (today,)).fetchone()[0]
        open_alerts = db.execute("""SELECT COUNT(*) FROM security_events e
<<<<<<< HEAD
            WHERE e.severity IN ('warning','severe')
            AND e.id NOT IN (SELECT event_id FROM acknowledged_events)""").fetchone()[0]
=======
            WHERE e.id NOT IN (SELECT event_id FROM acknowledged_events)""").fetchone()[0]
>>>>>>> 889d624ef29217e05c01da0b46d761ffd4ee4920
        device = db.execute("SELECT * FROM device_heartbeats ORDER BY last_seen DESC LIMIT 1").fetchone()
        orders = db.execute("SELECT COALESCE(SUM(boxes),0) FROM pickup_orders WHERE day=?", (today,)).fetchone()[0]
    online = False
    if device:
        try:
            online = (datetime.now(BUSINESS_TZ) - datetime.fromisoformat(device["last_seen"])).total_seconds() < 15
        except ValueError:
            online = False
    outside = dict(_external_camera_state["outside"])
    outside["scanned"] = _scans_today_allowed()
    outside["real_minutes"] = round(float(outside.get("max_seconds", 0)) * EXTERNAL_TIME_SCALE / 60, 1)
    return {"device_online": online, "alarm": current_alarm_level(), "cards": card_count,
            "scans_today": scan_count, "open_alerts": open_alerts, "authorized_boxes_today": orders,
<<<<<<< HEAD
            "time_scale": EXTERNAL_TIME_SCALE, "time_scale_mode": "DEMO" if EXTERNAL_TIME_SCALE != 1 else "REAL", "outside": outside, "inside": _external_camera_state["inside"]}


def _scans_recently_allowed(window_seconds: int = 120) -> int:
    cutoff = (datetime.now(BUSINESS_TZ) - timedelta(seconds=window_seconds)).isoformat(timespec="seconds")
    with db_session() as db:
        return int(db.execute("SELECT COUNT(*) FROM access_logs WHERE result='allow' AND event_at>=?", (cutoff,)).fetchone()[0])

=======
            "time_scale": EXTERNAL_TIME_SCALE, "outside": outside, "inside": _external_camera_state["inside"]}


>>>>>>> 889d624ef29217e05c01da0b46d761ffd4ee4920
def _scans_today_allowed() -> int:
    today = datetime.now(BUSINESS_TZ).date().isoformat()
    with db_session() as db:
        return int(db.execute("SELECT COUNT(DISTINCT uid) FROM access_logs WHERE result='allow' AND substr(event_at,1,10)=?", (today,)).fetchone()[0])

def _external_alert(level: str, kind: str, zone: str | None, message: str, uid: str | None = None, details: dict[str, Any] | None = None) -> None:
    """Persist one open compatibility alert, avoiding repeated duplicates from video frames."""
    with db_session() as db:
        rows = db.execute("SELECT id, details_json FROM security_events WHERE event_type=? AND severity IN ('warning','severe') ORDER BY id DESC LIMIT 100", (kind,)).fetchall()
        for row in rows:
            ack = db.execute("SELECT 1 FROM acknowledged_events WHERE event_id=?", (row["id"],)).fetchone()
            if ack:
                continue
            try: info = json.loads(row["details_json"] or "{}")
            except (TypeError, ValueError): info = {}
            if info.get("zone") == zone and info.get("uid") == uid:
                return
        db.execute("INSERT INTO security_events(event_at,event_type,track_id,severity,message,details_json) VALUES(?,?,?,?,?,?)",
                   (now_business(), kind, None, level, message, json.dumps({"zone": zone, "uid": uid, **(details or {})}, ensure_ascii=False)))

<<<<<<< HEAD
@app.post("/api/events", dependencies=[Depends(require_admin)])
def ingest_doan2_camera_event(payload: SecurityEventInput) -> dict[str, Any]:
    """Accept events from a compatible external camera script; native YOLO/ByteTrack remains independent."""
    scanned = _scans_recently_allowed(120)
    if payload.camera == "outside":
        _external_camera_state["outside"] = {"people": payload.people_in_zone, "max_seconds": payload.max_seconds, "ts": now_business()}
        real_minutes = payload.max_seconds * EXTERNAL_TIME_SCALE / 60
        # Heuristic only: compare current headcount with successful scans in the last 120 seconds, never whole-day totals.
        if payload.people_in_zone > scanned:
            _external_alert("warning", "possible_tailgating", "A",
                            f"Có {payload.people_in_zone} người trong khung hình và {scanned} lượt quẹt hợp lệ trong 120 giây gần nhất; cần xác minh thủ công.",
                            details={"people_in_zone": payload.people_in_zone, "valid_scans_last_120s": scanned, "heuristic": True})
=======
@app.post("/api/events")
def ingest_doan2_camera_event(payload: SecurityEventInput) -> dict[str, Any]:
    """Accept events from a compatible external camera script; native YOLO/ByteTrack remains independent."""
    scanned = _scans_today_allowed()
    if payload.camera == "outside":
        _external_camera_state["outside"] = {"people": payload.people_in_zone, "max_seconds": payload.max_seconds, "ts": now_business()}
        real_minutes = payload.max_seconds * EXTERNAL_TIME_SCALE / 60
        if payload.people_in_zone > scanned:
            _external_alert("warning", "tailgating", "A",
                            f"Camera ngoài ghi nhận {payload.people_in_zone} người nhưng chỉ {scanned} lượt quẹt hợp lệ.",
                            details={"people_in_zone": payload.people_in_zone, "scans_today": scanned})
>>>>>>> 889d624ef29217e05c01da0b46d761ffd4ee4920
        if real_minutes >= EXTERNAL_WARN_MINUTES:
            level = "severe" if real_minutes >= EXTERNAL_SEVERE_MINUTES else "warning"
            _external_alert(level, "loitering", "A", f"Phát hiện đứng lâu ở vùng A khoảng {real_minutes:.1f} phút.",
                            details={"seconds": payload.max_seconds, "real_minutes": real_minutes})
    elif payload.camera == "inside":
        view = []
        for person in payload.people:
            color = str(person.get("color") or "").strip()
            zone = str(person.get("zone") or "")
            seconds = float(person.get("seconds") or 0)
            with db_session() as db:
                card = db.execute("SELECT uid,name FROM cards WHERE upper(color)=upper(?) AND active=1 LIMIT 1", (color,)).fetchone() if color else None
                allowed_zones = {r["zone"] for r in db.execute("SELECT zone FROM card_permissions WHERE uid=?", (card["uid"],)).fetchall()} if card else set()
            wrong = bool(card and zone not in allowed_zones)
            if wrong:
                level = "severe" if zone in {"important", "critical"} else "warning"
                _external_alert(level, "wrong_zone", zone, f"{card['name']} đứng sai vùng {zone}.", card["uid"], {"color": color})
            real_minutes = seconds * EXTERNAL_TIME_SCALE / 60
            if zone in {"important", "critical"} and real_minutes >= EXTERNAL_WARN_MINUTES:
                level = "severe" if real_minutes >= EXTERNAL_SEVERE_MINUTES else "warning"
                _external_alert(level, "loitering", zone, f"Có người đứng lâu trong vùng {zone} khoảng {real_minutes:.1f} phút.", card["uid"] if card else None, {"color": color, "real_minutes": real_minutes})
            view.append({"color": color or None, "zone": zone, "name": card["name"] if card else None, "wrong": wrong})
        _external_camera_state["inside"] = view
        if len(payload.people) > scanned:
            _external_alert("warning", "headcount", None, f"Camera trong ghi nhận {len(payload.people)} người nhưng chỉ {scanned} lượt quẹt hợp lệ.", details={"people": len(payload.people), "scans_today": scanned})
        today = datetime.now(BUSINESS_TZ).date().isoformat()
        with db_session() as db:
            allowed_boxes = int(db.execute("SELECT COALESCE(SUM(boxes),0) FROM pickup_orders WHERE day=?", (today,)).fetchone()[0])
        if payload.boxes > allowed_boxes:
            _external_alert("severe", "boxes_over", None, f"Camera đếm {payload.boxes} thùng, hồ sơ cho phép {allowed_boxes} thùng.", details={"observed_boxes": payload.boxes, "authorized_boxes": allowed_boxes})
    if payload.event_type or payload.message:
        severity = payload.severity if payload.severity in {"info", "warning", "severe", "high", "critical"} else "warning"
        with db_session() as db:
            db.execute("INSERT INTO security_events(event_at,event_type,track_id,severity,message,details_json) VALUES(?,?,?,?,?,?)",
                       (now_business(), payload.event_type or "camera_event", None, severity, payload.message or "Sự kiện camera từ hệ thống ngoài.", json.dumps(payload.details, ensure_ascii=False)))
    return {"ok": True, "alarm": current_alarm_level(), "recorded": payload.camera in {"outside", "inside"} or bool(payload.event_type or payload.message)}



# Serve the selected KHO.DOAN2 web UI while keeping all API routes above it.
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="selected-web")
