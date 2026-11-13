"""Persistence and duplicate suppression for compatibility camera alerts."""
from __future__ import annotations

import json
from typing import Any, Callable


class ExternalAlertStore:
    def __init__(self, db_session: Callable[[], Any], now_business: Callable[[], str]) -> None:
        self.db_session = db_session
        self.now_business = now_business

    def persist(self, level: str, kind: str, zone: str | None, message: str,
                uid: str | None = None, details: dict[str, Any] | None = None) -> None:
        with self.db_session() as db:
            rows = db.execute(
                "SELECT id, details_json FROM security_events "
                "WHERE event_type=? AND severity IN ('warning','severe') ORDER BY id DESC LIMIT 100",
                (kind,),
            ).fetchall()
            for row in rows:
                if db.execute("SELECT 1 FROM acknowledged_events WHERE event_id=?", (row["id"],)).fetchone():
                    continue
                try:
                    info = json.loads(row["details_json"] or "{}")
                except (TypeError, ValueError):
                    info = {}
                if info.get("zone") == zone and info.get("uid") == uid:
                    return
            db.execute(
                "INSERT INTO security_events(event_at,event_type,track_id,severity,message,details_json) "
                "VALUES(?,?,?,?,?,?)",
                (self.now_business(), kind, None, level, message,
                 json.dumps({"zone": zone, "uid": uid, **(details or {})}, ensure_ascii=False)),
            )
