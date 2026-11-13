"""Administrator-only Telegram delivery diagnostics and retry routes."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request


def create_telegram_admin_router(services: Any) -> APIRouter:
    router = APIRouter()

    @router.get("/api/admin/telegram/status", dependencies=[Depends(services.require_admin)])
    def telegram_admin_status() -> dict[str, Any]:
        """Sensitive Telegram delivery diagnostics are available to admins only."""
        with services.db_session() as db:
            exists = db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='telegram_outbox'"
            ).fetchone()
            if not exists:
                return {"enabled": False, "pending": 0, "failed_permanent": 0, "last_success": None}
            counts = db.execute(
                "SELECT text_status,COUNT(*) AS n FROM telegram_outbox GROUP BY text_status"
            ).fetchall()
            pending = int(db.execute(
                "SELECT COUNT(*) FROM telegram_outbox WHERE text_status='pending' OR (text_status='sent' AND photo_status='pending')"
            ).fetchone()[0])
            photo_pending = int(db.execute(
                "SELECT COUNT(*) FROM telegram_outbox WHERE text_status='sent' AND photo_status='pending'"
            ).fetchone()[0])
            photo_failed = int(db.execute(
                "SELECT COUNT(*) FROM telegram_outbox WHERE photo_status='failed'"
            ).fetchone()[0])
            failed = sum(int(row["n"]) for row in counts if row["text_status"] == "failed_permanent")
            last_success = db.execute(
                "SELECT MAX(updated_at) FROM telegram_outbox WHERE text_status='sent'"
            ).fetchone()[0]
            lease = db.execute(
                "SELECT expires_at FROM telegram_instance_lease WHERE lease_name='bot'"
            ).fetchone()
            runtime_table = db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='telegram_runtime_state'"
            ).fetchone()
            runtime = ({row["state_key"]: row["state_value"] for row in db.execute(
                "SELECT state_key,state_value FROM telegram_runtime_state"
            ).fetchall()} if runtime_table else {})
            blocked = int(db.execute(
                "SELECT COUNT(DISTINCT chat_id) FROM telegram_outbox WHERE last_error LIKE '%HTTP 403%'"
            ).fetchone()[0])
            from ..telegram.bot import telegram_enabled
            return {
                "enabled": telegram_enabled(), "pending": pending,
                "photo_pending": photo_pending, "photo_failed": photo_failed,
                "failed_permanent": failed, "last_success": last_success,
                "blocked_chats": blocked, "circuit_breaker": runtime.get("circuit_breaker", "CLOSED"),
                "last_error": runtime.get("last_error"),
                "instance_lease_active": bool(lease and float(lease[0]) > services.epoch_time()),
            }

    @router.post(
        "/api/admin/telegram/retry/{chat_id}/{event_id}",
        dependencies=[Depends(services.require_admin)],
    )
    def telegram_retry_failed(chat_id: int, event_id: int, request: Request) -> dict[str, Any]:
        with services.db_session() as db:
            exists = db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='telegram_outbox'"
            ).fetchone()
            if not exists:
                raise HTTPException(status_code=404, detail="Telegram outbox chưa được khởi tạo.")
            cursor = db.execute(
                "UPDATE telegram_outbox SET text_status='pending',text_attempts=0,last_error=NULL,next_retry_at=NULL,updated_at=? "
                "WHERE chat_id=? AND event_id=? AND text_status='failed_permanent'",
                (services.now_business(), chat_id, event_id),
            )
            if cursor.rowcount != 1:
                raise HTTPException(status_code=404, detail="Không tìm thấy bản ghi gửi lỗi vĩnh viễn tương ứng.")
            db.execute(
                """INSERT INTO system_access_logs
                (event_at,event_type,operator_name,session_id,ip_address,user_agent,method,path,details)
                VALUES(?,?,?,?,?,?,?,?,?)""",
                (services.now_business(), "TELEGRAM_ADMIN_RETRY",
                 getattr(request.state, "khoai_operator_name", "admin"),
                 getattr(request.state, "khoai_session_digest", None),
                 request.client.host if request.client else None,
                 request.headers.get("user-agent", "")[:300], "POST", request.url.path,
                 f"chat_id={chat_id}; event_id={event_id}"),
            )
        return {"ok": True, "chat_id": chat_id, "event_id": event_id, "status": "pending"}

    return router
