"""Write-side callbacks for Telegram acknowledgements and outbox delivery."""
from __future__ import annotations
from datetime import datetime, timedelta
from typing import Any


def build_delivery_callbacks(backend: Any) -> dict[str, Any]:
    def audit(db: Any, action: str, actor: str, detail: str) -> None:
        db.execute("""INSERT INTO system_access_logs
            (event_at,event_type,operator_name,session_id,ip_address,user_agent,method,path,details)
            VALUES(?,?,?,?,?,?,?,?,?)""",
            (backend.now_business(), "TELEGRAM_ADMIN_ACTION", actor, None, None,
             "Telegram Bot", "BOT", action, detail[:500]))

    def acknowledge(event_id: int, actor: str) -> bool:
        with backend.db_session() as db:
            exists = db.execute("SELECT id FROM security_events WHERE id=?", (event_id,)).fetchone()
            if not exists: return False
            cursor = db.execute("INSERT OR IGNORE INTO acknowledged_events(event_id,acknowledged_at) VALUES(?,?)", (event_id, backend.now_business()))
            if cursor.rowcount:
                audit(db, f"/api/alerts/{event_id}/ack", actor, f"event_id={event_id}; source=telegram")
                return True
            return False

    def acknowledge_all(actor: str) -> int:
        with backend.db_session() as db:
            cursor = db.execute("""INSERT OR IGNORE INTO acknowledged_events(event_id,acknowledged_at)
                SELECT e.id, ? FROM security_events e LEFT JOIN acknowledged_events a ON a.event_id=e.id
                WHERE e.severity IN ('warning','severe') AND a.event_id IS NULL""", (backend.now_business(),))
            count = max(0, int(cursor.rowcount or 0))
            if count: audit(db, "/api/alerts/ack-all", actor, f"acknowledged_count={count}; source=telegram")
            return count

    def mark_text(chat_id: int,event_id: int,message_id: int) -> None:
        with backend.db_session() as db:
            db.execute("UPDATE telegram_outbox SET text_status='sent',text_message_id=?,text_attempts=text_attempts+1,last_error=NULL,updated_at=?,next_retry_at=NULL WHERE chat_id=? AND event_id=?",(message_id,backend.now_business(),chat_id,event_id))

    def retry_text(chat_id: int,event_id: int,error: str,delay: float,permanent: bool=False) -> None:
        with backend.db_session() as db:
            db.execute("UPDATE telegram_outbox SET text_attempts=text_attempts+1,text_status=?,last_error=?,next_retry_at=?,updated_at=? WHERE chat_id=? AND event_id=?",
                ("failed_permanent" if permanent else "pending",error[:300],(datetime.now(backend.BUSINESS_TZ)+timedelta(seconds=delay)).isoformat(timespec="seconds"),backend.now_business(),chat_id,event_id))

    def mark_photo(chat_id: int,event_id: int,status: str,message_id: int|None=None,error: str|None=None,delay: float=0) -> None:
        with backend.db_session() as db:
            db.execute("UPDATE telegram_outbox SET photo_status=?,photo_message_id=COALESCE(?,photo_message_id),photo_attempts=photo_attempts+1,last_error=?,next_retry_at=?,updated_at=? WHERE chat_id=? AND event_id=?",
                (status,message_id,(error or "")[:300] or None,(datetime.now(backend.BUSINESS_TZ)+timedelta(seconds=delay)).isoformat(timespec="seconds") if delay else None,backend.now_business(),chat_id,event_id))

    def lease(action: str, owner: str, ttl: int = 60) -> bool:
        # Evaluate wall-clock time inside SQLite, when the statement executes.
        # A Python timestamp captured before waiting for a database lock could
        # otherwise allow a delayed renew to extend an already-expired lease.
        db_now = "((julianday('now') - 2440587.5) * 86400.0)"
        with backend.db_session() as db:
            if action == "acquire":
                cur=db.execute(f"""INSERT INTO telegram_instance_lease(lease_name,owner,expires_at)
                    VALUES('bot',?,{db_now}+?) ON CONFLICT(lease_name) DO UPDATE SET
                    owner=excluded.owner,expires_at=excluded.expires_at
                    WHERE telegram_instance_lease.expires_at<={db_now} OR telegram_instance_lease.owner=?""",
                    (owner,ttl,owner))
                return cur.rowcount == 1
            if action == "renew":
                cur=db.execute(f"UPDATE telegram_instance_lease SET expires_at={db_now}+? WHERE lease_name='bot' AND owner=? AND expires_at>{db_now}",(ttl,owner)); return cur.rowcount==1
            db.execute("DELETE FROM telegram_instance_lease WHERE lease_name='bot' AND owner=?",(owner,)); return True

    def retry_permanent(chat_id: int,event_id: int) -> bool:
        with backend.db_session() as db:
            cur=db.execute("UPDATE telegram_outbox SET text_status='pending',text_attempts=0,last_error=NULL,next_retry_at=NULL,updated_at=? WHERE chat_id=? AND event_id=? AND text_status='failed_permanent'",(backend.now_business(),chat_id,event_id))
            return cur.rowcount==1

    def runtime_state(key: str, value: str) -> None:
        with backend.db_session() as db:
            db.execute("INSERT INTO telegram_runtime_state(state_key,state_value,updated_at) VALUES(?,?,?) ON CONFLICT(state_key) DO UPDATE SET state_value=excluded.state_value,updated_at=excluded.updated_at",(key,value[:300],backend.now_business()))

    def ops_status() -> dict[str, Any]:
        with backend.db_session() as db:
            counts=db.execute("SELECT text_status,COUNT(*) n FROM telegram_outbox GROUP BY text_status").fetchall()
            pending=int(db.execute("SELECT COUNT(*) FROM telegram_outbox WHERE text_status='pending' OR (text_status='sent' AND photo_status='pending')").fetchone()[0])
            failed=sum(int(r['n']) for r in counts if r['text_status']=='failed_permanent')
            photo_pending=int(db.execute("SELECT COUNT(*) FROM telegram_outbox WHERE text_status='sent' AND photo_status='pending'").fetchone()[0])
            photo_failed=int(db.execute("SELECT COUNT(*) FROM telegram_outbox WHERE photo_status='failed'").fetchone()[0])
            sent=db.execute("SELECT MAX(updated_at) FROM telegram_outbox WHERE text_status='sent'").fetchone()[0]
            blocked=int(db.execute("SELECT COUNT(DISTINCT chat_id) FROM telegram_outbox WHERE last_error LIKE '%HTTP 403%'").fetchone()[0])
            state={r['state_key']:r['state_value'] for r in db.execute("SELECT state_key,state_value FROM telegram_runtime_state").fetchall()}
            return {"pending":pending,"failed_permanent":failed,"last_success":sent,
                    "photo_pending":photo_pending,"photo_failed":photo_failed,
                    "blocked_chats":blocked,"circuit_breaker":state.get('circuit_breaker','CLOSED'),
                    "last_error":state.get('last_error')}
    return {
        "acknowledge": acknowledge, "acknowledge_all": acknowledge_all,
        "mark_text": mark_text, "retry_text": retry_text, "mark_photo": mark_photo,
        "lease": lease, "retry_permanent": retry_permanent,
        "ops_status": ops_status, "runtime_state": runtime_state,
    }
