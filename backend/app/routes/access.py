"""Access validation, track association and administrative audit routes."""
from __future__ import annotations

import json
import time
from datetime import date, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from ..schemas import AccessCheck, TrackAssociation


def check_access_impl(payload: AccessCheck, services: Any, *,
                      rfid_device_id: str | None = None,
                      rfid_debounce_seconds: float = 0.0) -> dict[str, Any]:
    uid = services.normalize_uid(payload.uid)
    with services.db_session() as db:
        db.execute("BEGIN IMMEDIATE")
        card = db.execute("SELECT * FROM cards WHERE uid = ?", (uid,)).fetchone()
        allowed_zones = [row["zone"] for row in db.execute(
            "SELECT zone FROM card_permissions WHERE uid=? ORDER BY zone", (uid,)
        ).fetchall()] if card else []
        name, reason = (card["name"], None) if card else (None, "unknown_card")
        today = services.today_business()
        deduplicated = False
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
                guard = None
                if rfid_device_id and rfid_debounce_seconds > 0:
                    guard = db.execute(
                        "SELECT last_allowed_at FROM rfid_scan_guard WHERE device_id=? AND uid=?",
                        (rfid_device_id, uid),
                    ).fetchone()
                if guard and time.time() - float(guard["last_allowed_at"]) < rfid_debounce_seconds:
                    deduplicated = True
                else:
                    db.execute(
                        "UPDATE cards SET used_today=0,last_reset_date=? WHERE uid=? AND (last_reset_date IS NULL OR last_reset_date<>?)",
                        (today, uid, today),
                    )
                    changed = db.execute(
                        "UPDATE cards SET used_today=used_today+1 WHERE uid=? AND active=1 AND used_today<daily_quota",
                        (uid,),
                    ).rowcount
                    if changed != 1:
                        reason = "quota_exhausted"
                    elif rfid_device_id and rfid_debounce_seconds > 0:
                        db.execute("""INSERT INTO rfid_scan_guard(device_id,uid,last_allowed_at)
                            VALUES(?,?,?) ON CONFLICT(device_id,uid) DO UPDATE SET
                            last_allowed_at=excluded.last_allowed_at""",
                            (rfid_device_id, uid, time.time()))
        allowed = reason is None
        result = "allow" if allowed else "deny"
        if not deduplicated:
            db.execute(
                "INSERT INTO access_logs(uid, card_name, event_at, result) VALUES (?, ?, ?, ?)",
                (uid, name, services.now_business(), result),
            )
            if reason:
                db.execute(
                    """INSERT INTO security_events(event_at,event_type,track_id,severity,message,details_json)
                       VALUES(?, ?, ?, ?, ?, ?)""",
                    (services.now_business(), "rfid_denied", payload.track_id, "warning",
                     f"Quẹt thẻ bị từ chối ({reason}): {name or uid}",
                     json.dumps({"uid": uid, "reason": reason}, ensure_ascii=False)),
                )
    associated = None
    if allowed and payload.track_id is not None:
        try:
            detector = services.detector_provider()
            if detector.has_rfid_ticket(uid):
                associated = detector.associate_card(payload.track_id, uid, name, allowed_zones=allowed_zones)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except Exception as exc:
            services.logger.exception("Không thể liên kết thẻ với camera")
            raise HTTPException(status_code=503, detail="Không thể liên kết thẻ với camera lúc này.") from exc
    return {
        "uid": uid, "allowed": allowed, "result": result,
        "deduplicated": deduplicated,
        "message": "cho phép" if allowed else "từ chối", "reason": reason, "name": name,
        "track_association": associated,
        "note": "Quẹt thẻ không tự xác định được ID người trên camera; cần truyền track_id nếu muốn liên kết.",
    }


def create_access_router(services: Any) -> APIRouter:
    router = APIRouter()

    @router.post("/api/access/check", dependencies=[Depends(services.require_admin)])
    def check_access(payload: AccessCheck) -> dict[str, Any]:
        return check_access_impl(payload, services)

    @router.post("/api/access/associate", dependencies=[Depends(services.require_admin)])
    def associate_access_track(payload: TrackAssociation) -> dict[str, Any]:
        uid = services.normalize_uid(payload.uid)
        cutoff = (datetime.now(services.business_tz) - timedelta(minutes=2)).isoformat(timespec="seconds")
        with services.db_session() as db:
            card = db.execute("SELECT uid,name,active FROM cards WHERE uid=?", (uid,)).fetchone()
            allowed_zones = [row["zone"] for row in db.execute(
                "SELECT zone FROM card_permissions WHERE uid=? ORDER BY zone", (uid,)
            ).fetchall()]
            recent_scan = db.execute(
                "SELECT id FROM access_logs WHERE uid=? AND result='allow' AND event_at>=? ORDER BY id DESC LIMIT 1",
                (uid, cutoff),
            ).fetchone()
        if not card or not card["active"] or not recent_scan:
            raise HTTPException(status_code=409, detail="Chỉ liên kết được thẻ đang hoạt động vừa được xác thực thành công trong 2 phút gần nhất.")
        try:
            detector = services.detector_provider()
            detector.start()
            association = detector.associate_card(payload.track_id, uid, card["name"], allowed_zones=allowed_zones)
            return {"ok": True, **association}
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except HTTPException:
            raise
        except Exception as exc:
            services.logger.exception("Không thể liên kết thẻ với Track ID")
            raise HTTPException(status_code=503, detail="Không thể liên kết thẻ với camera lúc này.") from exc

    @router.get("/api/system/access-logs", dependencies=[Depends(services.require_admin)])
    def list_system_access_logs(limit: int = Query(default=100, ge=1, le=500)) -> list[dict[str, Any]]:
        with services.db_session() as db:
            rows = db.execute(
                """SELECT id,event_at,event_type,operator_name,ip_address,user_agent,method,path,details
                   FROM system_access_logs ORDER BY id DESC LIMIT ?""",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    return router
