"""Read-side queries for device scan compatibility endpoints."""
from __future__ import annotations

import json
from typing import Any, Callable


class DeviceReadService:
    def __init__(self, db_session: Callable[[], Any], mask_uid: Callable[[str], str],
                 mask_uid_payload: Callable[[Any], Any]) -> None:
        self.db_session = db_session
        self.mask_uid = mask_uid
        self.mask_uid_payload = mask_uid_payload

    def list_scans(self, limit: int, is_admin: bool) -> list[dict[str, Any]]:
        """Return the legacy KHO.DOAN2 scan shape with role-aware UID masking."""
        with self.db_session() as db:
            rows = db.execute(
                "SELECT id, uid, card_name, event_at, result FROM access_logs ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
            records = []
            for row in rows:
                item = dict(row)
                item["ts"] = item.pop("event_at")
                item["name"] = item.pop("card_name")
                item["reason"] = None
                if item["result"] == "deny":
                    denied = db.execute(
                        "SELECT details_json FROM security_events WHERE event_type='rfid_denied' AND details_json LIKE ? ORDER BY id DESC LIMIT 1",
                        (f'%"uid": "{item["uid"]}"%',),
                    ).fetchone()
                    if denied:
                        try:
                            item["reason"] = json.loads(denied["details_json"]).get("reason")
                        except (ValueError, TypeError):
                            pass
                records.append(item)
        return records if is_admin else self.mask_uid_payload(records)

    def last_unknown_card(self, is_admin: bool) -> dict[str, Any]:
        with self.db_session() as db:
            row = db.execute(
                "SELECT uid,event_at FROM access_logs WHERE result='deny' ORDER BY id DESC"
            ).fetchone()
        uid = row["uid"] if row else None
        if uid and not is_admin:
            uid = self.mask_uid(uid)
        return {"uid": uid, "ts": row["event_at"] if row else None}
