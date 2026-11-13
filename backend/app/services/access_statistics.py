"""Read-only access-log statistics used by dashboard and external-event rules."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Callable


class AccessStatisticsService:
    def __init__(self, db_session: Callable[[], Any], business_tz: Any) -> None:
        self.db_session = db_session
        self.business_tz = business_tz

    def recently_allowed(self, window_seconds: int = 120) -> int:
        cutoff = (datetime.now(self.business_tz) - timedelta(seconds=window_seconds)).isoformat(timespec="seconds")
        with self.db_session() as db:
            row = db.execute(
                "SELECT COUNT(*) FROM access_logs WHERE result='allow' AND event_at>=?", (cutoff,)
            ).fetchone()
        return int(row[0])

    def today_allowed(self) -> int:
        today = datetime.now(self.business_tz).date().isoformat()
        with self.db_session() as db:
            row = db.execute(
                "SELECT COUNT(DISTINCT uid) FROM access_logs WHERE result='allow' AND substr(event_at,1,10)=?",
                (today,),
            ).fetchone()
        return int(row[0])
