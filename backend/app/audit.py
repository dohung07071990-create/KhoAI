"""Admin action audit middleware."""
from __future__ import annotations

import asyncio
import logging
import time

from .auth import db_session, now_business

logger = logging.getLogger("khoai")

class AdminAuditMiddleware:
    """Pure ASGI audit middleware; SQLite writes run off the event loop."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        status_code = 500

        async def send_with_status(message):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = int(message.get("status", 500))
            await send(message)

        await self.app(scope, receive, send_with_status)
        state = scope.setdefault("state", {})
        method = str(scope.get("method", "GET")).upper()
        path = str(scope.get("path", ""))
        digest = state.get("khoai_session_digest")
        excluded = ("/api/rfid/scan", "/api/events", "/api/device/")
        if not (digest and state.get("khoai_role") == "admin" and path.startswith("/api/")
                and method in {"POST", "PUT", "PATCH", "DELETE"}
                and not any(path.startswith(item) for item in excluded)):
            return
        headers = {key.decode("latin1").lower(): value.decode("latin1") for key, value in scope.get("headers", [])}
        client = scope.get("client")
        ip = client[0] if client else "unknown"
        actor = state.get("khoai_operator_name") or "Quản trị viên"
        user_agent = headers.get("user-agent", "")[:300]

        def write_audit():
            with db_session() as db:
                session = db.execute("SELECT operator_name,expires_at FROM admin_sessions WHERE session_id=?", (digest,)).fetchone()
                operator = session["operator_name"] if session and float(session["expires_at"]) > time.time() else actor
                db.execute("""INSERT INTO system_access_logs
                    (event_at,event_type,operator_name,session_id,ip_address,user_agent,method,path,details)
                    VALUES(?,?,?,?,?,?,?,?,?)""",
                    (now_business(), "ADMIN_ACTION", operator, digest[:16], ip,
                     user_agent, method, path, f"HTTP {status_code}"))
        try:
            await asyncio.to_thread(write_audit)
        except Exception:
            logger.exception("Không ghi được nhật ký thao tác quản trị")

