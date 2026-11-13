"""Administrator card registry routes."""
from __future__ import annotations

import sqlite3
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from ..schemas import CardCreate, CardUpdate


def create_cards_router(services: Any) -> APIRouter:
    router = APIRouter()

    @router.get("/api/cards", dependencies=[Depends(services.require_admin)])
    def list_cards() -> list[dict[str, Any]]:
        with services.db_session() as db:
            rows = db.execute(
                "SELECT uid, name, age, active, created_at, expires_at, daily_quota, used_today, color "
                "FROM cards ORDER BY created_at DESC"
            ).fetchall()
            cards = []
            for row in rows:
                item = dict(row)
                item["zones"] = [r["zone"] for r in db.execute(
                    "SELECT zone FROM card_permissions WHERE uid=? ORDER BY zone", (item["uid"],)
                ).fetchall()]
                order = db.execute(
                    "SELECT item, boxes FROM pickup_orders WHERE uid=? ORDER BY id DESC LIMIT 1",
                    (item["uid"],),
                ).fetchone()
                item["item"] = order["item"] if order else None
                item["boxes"] = order["boxes"] if order else 0
                cards.append(item)
        return cards

    @router.post("/api/cards", status_code=201, dependencies=[Depends(services.require_admin)])
    def create_card(payload: CardCreate) -> dict[str, Any]:
        uid, name, created_at = services.normalize_uid(payload.uid), payload.name.strip(), services.now_business()
        if not name:
            raise HTTPException(status_code=422, detail="Tên người không được để trống.")
        try:
            with services.db_session() as db:
                db.execute(
                    """INSERT INTO cards(uid, name, age, active, created_at, expires_at, daily_quota,
                       used_today, last_reset_date, color) VALUES (?, ?, ?, 1, ?, ?, ?, 0, ?, ?)""",
                    (uid, name, payload.age if payload.age is not None else 0, created_at,
                     payload.expires_at, payload.daily_quota, services.today_business(), payload.color),
                )
                db.execute("DELETE FROM card_permissions WHERE uid = ?", (uid,))
                for zone in payload.zones:
                    if zone not in {"entry", "exit", "important", "critical", "external_usb_zone"}:
                        raise HTTPException(status_code=422, detail=f"Vùng không hợp lệ: {zone}")
                    db.execute("INSERT INTO card_permissions(uid, zone) VALUES (?, ?)", (uid, zone))
                if payload.item and payload.boxes:
                    db.execute(
                        "INSERT INTO pickup_orders(uid,item,boxes,zone,day) VALUES(?,?,?,?,?)",
                        (uid, payload.item.strip(), payload.boxes,
                         payload.zones[0] if payload.zones else None, services.today_business()),
                    )
        except sqlite3.IntegrityError as exc:
            raise HTTPException(status_code=409, detail="UID này đã được cấp thẻ.") from exc
        return {
            "uid": uid, "name": name, "age": payload.age if payload.age is not None else 0,
            "active": True, "created_at": created_at, "expires_at": payload.expires_at,
            "daily_quota": payload.daily_quota, "color": payload.color, "zones": payload.zones,
            "item": payload.item, "boxes": payload.boxes,
        }

    @router.patch("/api/cards/{uid}", dependencies=[Depends(services.require_admin)])
    def update_card(uid: str, payload: CardUpdate) -> dict[str, Any]:
        normalized = services.normalize_uid(uid)
        with services.db_session() as db:
            row = db.execute("SELECT uid,name,active FROM cards WHERE uid=?", (normalized,)).fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Không tìm thấy thẻ.")
            db.execute("UPDATE cards SET active=? WHERE uid=?", (1 if payload.active else 0, normalized))
        revocation = {"revoked": 0, "revoked_track_ids": []}
        if not payload.active:
            try:
                services.detector_provider().revoke_uid(normalized)
            except Exception as exc:
                services.logger.exception("Không thể thu hồi quyền detector của UID %s", normalized)
                raise HTTPException(
                    status_code=503,
                    detail="Đã khóa thẻ trong CSDL nhưng chưa xác nhận thu hồi quyền camera; cần kiểm tra detector.",
                ) from exc
        return {"ok": True, "uid": normalized, "active": payload.active, "revocation": revocation}

    @router.delete("/api/cards/{uid}", dependencies=[Depends(services.require_admin)])
    def delete_card_compat(uid: str) -> dict[str, Any]:
        """Delete a card without deleting historical access/security logs."""
        normalized = services.normalize_uid(uid)
        with services.db_session() as db:
            exists = db.execute("SELECT uid FROM cards WHERE uid=?", (normalized,)).fetchone()
            if not exists:
                raise HTTPException(status_code=404, detail="Không tìm thấy thẻ.")
            db.execute("DELETE FROM card_permissions WHERE uid=?", (normalized,))
            db.execute("DELETE FROM pickup_orders WHERE uid=?", (normalized,))
            db.execute("DELETE FROM cards WHERE uid=?", (normalized,))
        try:
            services.detector_provider().revoke_uid(normalized)
        except Exception as exc:
            services.logger.exception("Không thể thu hồi quyền detector của UID đã xóa %s", normalized)
            raise HTTPException(
                status_code=503,
                detail="Đã xóa thẻ trong CSDL nhưng chưa xác nhận thu hồi quyền camera.",
            ) from exc
        return {"ok": True}

    return router
