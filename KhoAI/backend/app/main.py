from __future__ import annotations

import os
import re
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIR = ROOT / "frontend"
PUBLIC_DIR = ROOT / "public"
DB_PATH = Path(os.getenv("DB_PATH", str(ROOT / "data" / "khoai.sqlite3")))
BUSINESS_TZ = ZoneInfo(os.getenv("BUSINESS_TIMEZONE", "Asia/Ho_Chi_Minh"))
UID_RE = re.compile(r"^[0-9A-Fa-f]{4,20}$")

app = FastAPI(title="Kho AI – API mẫu", version="0.1.0")


def connect_db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
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
    with db_session() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS cards (
                uid TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                age INTEGER NOT NULL CHECK (age BETWEEN 0 AND 120),
                active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS access_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                uid TEXT NOT NULL,
                card_name TEXT,
                event_at TEXT NOT NULL,
                result TEXT NOT NULL CHECK (result IN ('allow', 'deny'))
            );
            CREATE INDEX IF NOT EXISTS idx_access_logs_event_at ON access_logs(event_at DESC);
            """
        )


def now_business() -> str:
    return datetime.now(BUSINESS_TZ).isoformat(timespec="seconds")


def normalize_uid(uid: str) -> str:
    normalized = re.sub(r"[\s:-]", "", uid).upper()
    if not UID_RE.fullmatch(normalized):
        raise HTTPException(status_code=422, detail="UID phải gồm 4–20 ký tự hex (0–9, A–F).")
    return normalized


class CardCreate(BaseModel):
    uid: str = Field(min_length=4, max_length=24)
    name: str = Field(min_length=1, max_length=100)
    age: int = Field(ge=0, le=120)


class AccessCheck(BaseModel):
    uid: str = Field(min_length=4, max_length=24)


class CameraZoneUpdate(BaseModel):
    points: list[list[float]] = Field(min_length=3, max_length=30)


init_db()


@app.get("/", include_in_schema=False)
def home() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/manus-routes.json", include_in_schema=False)
def route_manifest() -> FileResponse:
    return FileResponse(PUBLIC_DIR / "manus-routes.json", media_type="application/json")


app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "kho-ai-demo"}


@app.get("/api/cards")
def list_cards() -> list[dict[str, Any]]:
    with db_session() as db:
        rows = db.execute(
            "SELECT uid, name, age, active, created_at FROM cards ORDER BY created_at DESC"
        ).fetchall()
    return [dict(row) for row in rows]


@app.post("/api/cards", status_code=201)
def create_card(payload: CardCreate) -> dict[str, Any]:
    uid = normalize_uid(payload.uid)
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Tên người không được để trống.")
    created_at = now_business()
    try:
        with db_session() as db:
            db.execute(
                "INSERT INTO cards(uid, name, age, active, created_at) VALUES (?, ?, ?, 1, ?)",
                (uid, name, payload.age, created_at),
            )
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=409, detail="UID này đã được cấp thẻ.") from exc
    return {"uid": uid, "name": name, "age": payload.age, "active": True, "created_at": created_at}


@app.post("/api/access/check")
def check_access(payload: AccessCheck) -> dict[str, Any]:
    uid = normalize_uid(payload.uid)
    with db_session() as db:
        card = db.execute(
            "SELECT name, active FROM cards WHERE uid = ?", (uid,)
        ).fetchone()
        allowed = bool(card and card["active"])
        name = card["name"] if card else None
        result = "allow" if allowed else "deny"
        db.execute(
            "INSERT INTO access_logs(uid, card_name, event_at, result) VALUES (?, ?, ?, ?)",
            (uid, name, now_business(), result),
        )
    return {
        "uid": uid,
        "allowed": allowed,
        "result": result,
        "message": "cho phép" if allowed else "từ chối",
        "name": name,
    }


@app.get("/api/logs")
def list_logs(limit: int = Query(default=100, ge=1, le=500)) -> list[dict[str, Any]]:
    with db_session() as db:
        rows = db.execute(
            "SELECT id, uid, card_name, event_at, result FROM access_logs "
            "ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


@app.get("/api/stats")
def stats() -> dict[str, int]:
    today = datetime.now(BUSINESS_TZ).date().isoformat()
    with db_session() as db:
        cards = db.execute("SELECT COUNT(*) FROM cards WHERE active = 1").fetchone()[0]
        scans_today = db.execute(
            "SELECT COUNT(*) FROM access_logs WHERE substr(event_at, 1, 10) = ?", (today,)
        ).fetchone()[0]
        denied_today = db.execute(
            "SELECT COUNT(*) FROM access_logs WHERE substr(event_at, 1, 10) = ? AND result = 'deny'",
            (today,),
        ).fetchone()[0]
    return {"active_cards": cards, "scans_today": scans_today, "denied_today": denied_today}


@app.get("/api/camera/status")
def camera_status() -> dict[str, Any]:
    camera_available = False
    person_in_zone = False
    camera_error: str | None = None
    try:
        from ai.person_detector import detector  # optional AI dependencies

        camera_available = detector.camera_available
        if not camera_available:
            camera_available = detector.read_jpeg() is not None
        person_in_zone = bool(detector.person_in_zone)
    except Exception as exc:  # camera or optional packages may be unavailable
        camera_error = str(exc)[:240]
    tracked_ids: list[int] = []
    last_event = None
    try:
        from ai.person_detector import detector
        tracked_ids = list(detector.tracked_person_ids)
        last_event = detector.last_event
    except Exception:
        pass
    return {
        "usb_available": camera_available,
        "person_in_zone": person_in_zone,
        "tracked_person_ids": tracked_ids,
        "last_intrusion_event": last_event,
        "tracker": "ByteTrack",
        "usb_stream": "/api/camera/stream.mjpg" if camera_available else None,
        "error": camera_error,
        "note": "Camera USB phải cắm vào máy đang chạy FastAPI.",
    }


@app.get("/api/camera/zone")
def get_camera_zone() -> dict[str, Any]:
    from ai.person_detector import detector
    return {"points": [list(point) for point in detector.zone], "coordinate_system": "normalized_0_to_1"}


@app.put("/api/camera/zone")
def update_camera_zone(payload: CameraZoneUpdate) -> dict[str, Any]:
    from ai.person_detector import detector
    try:
        detector.set_zone([(point[0], point[1]) for point in payload.points], save=True)
    except (ValueError, IndexError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"saved": True, "points": [list(point) for point in detector.zone], "file": "ai/zone.json"}


@app.get("/api/camera/events")
def camera_events(limit: int = Query(default=30, ge=1, le=100)) -> list[dict[str, Any]]:
    from ai.person_detector import detector
    return detector.get_events(limit)


def mjpeg_frames():
    try:
        from ai.person_detector import detector
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Chưa cài module camera AI: {exc}") from exc

    last_frame_at = time.monotonic()
    while True:
        frame = detector.read_jpeg()
        if frame is None:
            if time.monotonic() - last_frame_at > 10:
                break
            time.sleep(0.2)
            continue
        last_frame_at = time.monotonic()
        yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"


@app.get("/api/camera/stream.mjpg")
def camera_stream() -> StreamingResponse:
    return StreamingResponse(
        mjpeg_frames(),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
    )


@app.on_event("shutdown")
def shutdown_camera() -> None:
    try:
        from ai.person_detector import detector

        detector.close()
    except Exception:
        pass
