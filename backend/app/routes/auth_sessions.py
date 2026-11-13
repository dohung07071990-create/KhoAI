"""Login, current-session, and logout HTTP endpoints."""
from __future__ import annotations

import secrets
from typing import Any, Callable

from fastapi import APIRouter, HTTPException, Request, Response

from ..schemas import AdminLogin


def create_auth_session_router(services: Any) -> APIRouter:
    router = APIRouter()

    @router.post("/api/auth/login")
    def account_login(payload: AdminLogin, request: Request, response: Response) -> dict[str, Any]:
        ip = request.client.host if request.client else "unknown"
        now = services.monotonic()
        with services.auth_lock:
            recent = [stamp for stamp in services.auth_failures[ip]
                      if now - stamp < services.auth_rate_window]
            services.auth_failures[ip] = recent
            if len(recent) >= services.auth_rate_limit:
                raise HTTPException(status_code=429, detail="Quá nhiều lần đăng nhập thất bại; thử lại sau.")
        with services.db_session() as db:
            row = db.execute(
                "SELECT * FROM admin_users WHERE username=? COLLATE NOCASE AND active=1",
                (payload.username.strip(),),
            ).fetchone()
        stored_hash = row["password_hash"] if row else services.dummy_password_hash()
        password_ok = services.verify_credential_hash(payload.password, stored_hash)
        if not row or not password_ok:
            services.record_auth_failure(ip)
            with services.db_session() as db:
                db.execute(
                    "INSERT INTO system_access_logs(event_at,event_type,operator_name,ip_address,user_agent,details) VALUES(?,?,?,?,?,?)",
                    (services.now_business(), "LOGIN_FAILED", payload.username[:80], ip,
                     request.headers.get("user-agent", "")[:300],
                     "Sai thông tin đăng nhập hoặc tài khoản bị khóa."),
                )
            raise HTTPException(status_code=401, detail="Tên đăng nhập hoặc mật khẩu không đúng.")
        with services.auth_lock:
            services.auth_failures.pop(ip, None)
        try:
            rounds = int(str(row["password_hash"]).split("$", 2)[1])
        except (ValueError, IndexError):
            rounds = 0
        sid = secrets.token_urlsafe(32)
        now_epoch = services.epoch_time()
        name = row["display_name"]
        with services.db_session() as db:
            if rounds < 600_000:
                db.execute("UPDATE admin_users SET password_hash=? WHERE user_id=?",
                           (services.hash_credential(payload.password), row["user_id"]))
            db.execute("DELETE FROM admin_sessions WHERE expires_at<=?", (now_epoch,))
            digest = services.session_digest(sid)
            if digest is None:
                raise RuntimeError("Không thể tạo mã hash cho admin session")
            db.execute(
                "INSERT INTO admin_sessions(session_id,created_at,expires_at,operator_name,user_id,role) VALUES(?,?,?,?,?,?)",
                (digest, now_epoch, now_epoch + services.session_seconds, name, row["user_id"], row["role"]),
            )
            db.execute(
                "INSERT INTO system_access_logs(event_at,event_type,operator_name,session_id,ip_address,user_agent,details) VALUES(?,?,?,?,?,?,?)",
                (services.now_business(), "LOGIN", name, digest[:16], ip,
                 request.headers.get("user-agent", "")[:300],
                 f"Đăng nhập tài khoản {row['username']} ({row['role']})."),
            )
        response.set_cookie(
            "khoai_admin_session", sid, httponly=True,
            secure=request.url.scheme == "https", samesite="strict", path="/",
            max_age=services.session_seconds,
        )
        return {"ok": True, "username": row["username"], "display_name": name, "role": row["role"]}

    @router.get("/api/auth/me")
    def account_me(request: Request) -> dict[str, Any]:
        session = services.load_session(request.cookies.get("khoai_admin_session"))
        if not session:
            raise HTTPException(status_code=401, detail="Chưa đăng nhập.")
        return {"display_name": session["operator_name"], "role": session["role"],
                "username": session.get("username") or "legacy-token"}

    @router.post("/api/logout")
    def admin_logout(request: Request, response: Response) -> dict[str, bool]:
        session_id = request.cookies.get("khoai_admin_session")
        if session_id:
            ip = request.client.host if request.client else "unknown"
            digest = services.session_digest(session_id)
            if digest is not None:
                with services.db_session() as db:
                    session = db.execute(
                        "SELECT operator_name FROM admin_sessions WHERE session_id=?", (digest,)
                    ).fetchone()
                    if session:
                        db.execute(
                            "INSERT INTO system_access_logs(event_at,event_type,operator_name,session_id,ip_address,user_agent,details) VALUES(?,?,?,?,?,?,?)",
                            (services.now_business(), "LOGOUT", session["operator_name"], digest[:16], ip,
                             request.headers.get("user-agent", "")[:300], "Đăng xuất chủ động."),
                        )
                    db.execute("DELETE FROM admin_sessions WHERE session_id=?", (digest,))
        response.delete_cookie("khoai_admin_session", path="/")
        return {"success": True}

    return router
