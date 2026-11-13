"""Command operations for acknowledging incidents and silencing sirens."""
from __future__ import annotations

from collections.abc import Callable
from typing import Any


class IncidentCommandService:
    """Own write-side incident commands; HTTP authorization stays in the router."""

    def __init__(
        self,
        db_session: Callable[[], Any],
        now_business: Callable[[], str],
        close_incident_if_resolved: Callable[[Any], None],
        incident_status: Callable[[], dict[str, Any]],
    ) -> None:
        self.db_session = db_session
        self.now_business = now_business
        self.close_incident_if_resolved = close_incident_if_resolved
        self.incident_status = incident_status

    def acknowledge_all(self) -> dict[str, Any]:
        stamp = self.now_business()
        with self.db_session() as db:
            cursor = db.execute(
                "UPDATE incidents SET acknowledged=1, acknowledged_at=?, updated_at=? "
                "WHERE status='OPEN' AND acknowledged=0",
                (stamp, stamp),
            )
            acknowledged_count = max(0, int(cursor.rowcount or 0))
            self.close_incident_if_resolved(db)
        return {"ok": True, "acknowledged_count": acknowledged_count, **self.incident_status()}

    def silence_sirens(self) -> dict[str, Any]:
        stamp = self.now_business()
        with self.db_session() as db:
            cursor = db.execute(
                "UPDATE incidents SET siren_until=0, updated_at=? "
                "WHERE status='OPEN' AND siren_until>0",
                (stamp,),
            )
            stopped_count = max(0, int(cursor.rowcount or 0))
        return {"ok": True, "stopped_count": stopped_count, **self.incident_status()}
