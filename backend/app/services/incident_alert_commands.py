"""Write-side commands for acknowledging individual security alerts."""
from __future__ import annotations
from collections.abc import Callable
from typing import Any

class IncidentAlertCommandService:
    def __init__(self, db_session: Callable[[], Any], now_business: Callable[[], str],
                 current_alarm_level: Callable[[], str]) -> None:
        self.db_session = db_session
        self.now_business = now_business
        self.current_alarm_level = current_alarm_level

    def acknowledge(self, event_id: int) -> dict[str, Any]:
        with self.db_session() as db:
            exists = db.execute("SELECT id FROM security_events WHERE id=?", (event_id,)).fetchone()
            if not exists:
                from fastapi import HTTPException
                raise HTTPException(status_code=404, detail="Không tìm thấy cảnh báo.")
            db.execute("INSERT OR IGNORE INTO acknowledged_events(event_id,acknowledged_at) VALUES(?,?)", (event_id, self.now_business()))
        return {"ok": True, "alarm": self.current_alarm_level()}
