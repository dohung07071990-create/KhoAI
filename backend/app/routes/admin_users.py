"""Administrator account CRUD endpoints."""
from __future__ import annotations

import sqlite3
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from ..schemas import AdminUserCreate, AdminUserUpdate


def create_admin_users_router(services: Any) -> APIRouter:
    router = APIRouter()

    @router.get("/api/admin/users", dependencies=[Depends(services.require_admin)])
    def list_admin_users() -> list[dict[str, Any]]:
        with services.db_session() as db:
            rows = db.execute(
                "SELECT user_id,username,display_name,role,active,created_at FROM admin_users ORDER BY user_id"
            ).fetchall()
        return [dict(row) for row in rows]

    @router.post("/api/admin/users", dependencies=[Depends(services.require_admin)])
    def create_admin_user(payload: AdminUserCreate) -> dict[str, Any]:
        try:
            with services.db_session() as db:
                cur = db.execute(
                    "INSERT INTO admin_users(username,display_name,password_hash,role,created_at) VALUES(?,?,?,?,?)",
                    (payload.username, payload.display_name, services.hash_credential(payload.password),
                     payload.role, services.now_business()),
                )
                return {"user_id": cur.lastrowid, "username": payload.username, "role": payload.role}
        except sqlite3.IntegrityError as exc:
            raise HTTPException(status_code=409, detail="Tên đăng nhập đã tồn tại.") from exc

    @router.patch("/api/admin/users/{user_id}", dependencies=[Depends(services.require_admin)])
    def update_admin_user(user_id: int, payload: AdminUserUpdate, request: Request) -> dict[str, Any]:
        changes = payload.model_dump(exclude_unset=True)
        if not changes:
            raise HTTPException(status_code=400, detail="Không có trường nào cần cập nhật.")
        with services.db_session() as db:
            # Serialize the admin-count check with account changes so two
            # concurrent requests cannot both remove the last active admin.
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT user_id,role,active FROM admin_users WHERE user_id=?", (user_id,)).fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Không tìm thấy tài khoản.")
            current_user_id = getattr(request.state, "khoai_user_id", None)
            will_be_admin = (changes.get("role", row["role"]) == "admin"
                             and changes.get("active", bool(row["active"])) is not False)
            if current_user_id == user_id and not will_be_admin:
                raise HTTPException(status_code=409, detail="Không thể tự hạ quyền hoặc vô hiệu hóa tài khoản đang sử dụng.")
            active_admins = int(db.execute(
                "SELECT COUNT(*) FROM admin_users WHERE active=1 AND role='admin'"
            ).fetchone()[0])
            target_loses_admin = row["active"] == 1 and row["role"] == "admin" and not will_be_admin
            if target_loses_admin and active_admins <= 1:
                raise HTTPException(status_code=409, detail="Không thể vô hiệu hóa hoặc hạ quyền admin cuối cùng.")
            for key, value in changes.items():
                stored_value = (services.hash_credential(value) if key == "password"
                                else (int(value) if key == "active" else value))
                column = "password_hash" if key == "password" else key
                db.execute(f"UPDATE admin_users SET {column}=? WHERE user_id=?", (stored_value, user_id))
            if any(key in changes for key in ("active", "role", "password")):
                db.execute("DELETE FROM admin_sessions WHERE user_id=?", (user_id,))
            updated = db.execute(
                "SELECT user_id,username,display_name,role,active,created_at FROM admin_users WHERE user_id=?",
                (user_id,),
            ).fetchone()
        return dict(updated)

    return router
