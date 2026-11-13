"""Read-side callbacks for Telegram status, alerts, evidence and delivery."""
from __future__ import annotations
import json
import os
import re
from pathlib import Path
from typing import Any
from .privacy import mask_telegram_event


def build_query_callbacks(backend: Any) -> dict[str, Any]:
    def status() -> dict[str, Any]:
        today = backend.today_business()
        with backend.db_session() as db:
            total = int(db.execute("SELECT COUNT(*) FROM security_events WHERE severity IN ('warning','severe') AND id NOT IN (SELECT event_id FROM acknowledged_events)").fetchone()[0])
            scans = int(db.execute("SELECT COUNT(*) FROM access_logs WHERE substr(event_at,1,10)=?", (today,)).fetchone()[0])
            device = db.execute("SELECT last_seen FROM device_heartbeats ORDER BY last_seen DESC LIMIT 1").fetchone()
        camera = "unknown"
        try:
            from ai.person_detector import detector
            camera = str(detector.status().get("camera_health", "unknown"))
        except Exception:
            pass
        return {"Phiên bản": backend.APP_VERSION, "Camera AI": camera,
                "Cảnh báo chưa xử lý": total, "Lượt quẹt hôm nay": scans,
                "Thiết bị gần nhất": device["last_seen"] if device else "chưa có heartbeat"}

    def alerts(limit: int) -> list[dict[str, Any]]:
        with backend.db_session() as db:
            rows = db.execute("""SELECT e.id,e.event_at,e.event_type,e.severity,e.message,e.details_json
                FROM security_events e LEFT JOIN acknowledged_events a ON a.event_id=e.id
                WHERE e.severity IN ('warning','severe') AND a.event_id IS NULL
                ORDER BY e.id DESC LIMIT ?""", (limit,)).fetchall()
            cards = db.execute("SELECT uid,name FROM cards").fetchall()
        known_uids = {str(row["uid"]) for row in cards if row["uid"]}
        known_names = {str(row["name"]) for row in cards if row["name"]}
        include_name = os.getenv("TELEGRAM_INCLUDE_PERSON_NAME", "0").strip().lower() in {"1", "true", "yes"}
        return [mask_telegram_event(dict(row), known_uids, known_names, include_name) for row in rows]

    def snapshot() -> bytes | None:
        try:
            from ai.person_detector import detector
            return detector.latest_jpeg()
        except Exception:
            return None

    def event_evidence(event_id: int) -> dict[str, Any]:
        with backend.db_session() as db:
            row = db.execute("SELECT details_json,event_at FROM security_events WHERE id=?", (event_id,)).fetchone()
            if not row: return {"status": "expired", "photo": None}
        try: details = json.loads(row["details_json"] or "{}")
        except (TypeError, ValueError): details = {}
        state = str(details.get("evidence_status") or ("pending" if details.get("evidence_pending") else "not_applicable")).lower()
        raw = details.get("evidence_filename") or str(details.get("evidence_url") or "").rsplit("/", 1)[-1]
        name = Path(str(raw)).name
        if name and name == raw and re.fullmatch(r"[0-9a-f]{32,36}\.jpg", name):
            try:
                from ai.person_detector import EVIDENCE_DIR
                path = Path(EVIDENCE_DIR) / name
                if path.is_file(): return {"status": "available", "photo": path.read_bytes()}
                if state == "available": state = "expired"
            except Exception: pass
        return {"status": state if state in {"pending", "failed", "expired", "not_applicable"} else "not_applicable", "photo": None}

    def discover_events(chat_id: int, limit: int = 100) -> int:
        now = backend.now_business()
        with backend.db_session() as db:
            state = db.execute("SELECT last_event_id FROM telegram_delivery_state WHERE chat_id=?", (chat_id,)).fetchone()
            last_id = int(state[0]) if state else 0
            rows = db.execute("SELECT id,event_at,severity FROM security_events WHERE id>? AND severity IN ('warning','severe') ORDER BY id LIMIT ?", (last_id, limit)).fetchall()
            for row in rows:
                db.execute("""INSERT OR IGNORE INTO telegram_outbox
                    (chat_id,event_id,severity,event_at,text_status,photo_status,created_at,updated_at)
                    VALUES(?,?,?,?,'pending','pending',?,?)""", (chat_id,int(row['id']),row['severity'],row['event_at'],now,now))
                db.execute("UPDATE telegram_delivery_state SET last_event_id=MAX(last_event_id,?) WHERE chat_id=?", (int(row['id']),chat_id))
            return len(rows)

    def due_items(chat_id: int, limit: int = 30) -> list[dict[str, Any]]:
        now = backend.now_business()
        with backend.db_session() as db:
            rows = db.execute("""SELECT o.*,e.event_type,e.message,e.details_json,
                EXISTS(SELECT 1 FROM acknowledged_events a WHERE a.event_id=e.id) AS acknowledged
                FROM telegram_outbox o JOIN security_events e ON e.id=o.event_id
                WHERE o.chat_id=? AND o.text_status!='failed_permanent'
                  AND (o.next_retry_at IS NULL OR o.next_retry_at<=?)
                  AND (o.text_status='pending' OR (o.text_status='sent' AND o.photo_status='pending'))
                ORDER BY o.event_id LIMIT ?""", (chat_id,now,limit)).fetchall()
        output=[]
        include_name=os.getenv("TELEGRAM_INCLUDE_PERSON_NAME","0").strip().lower() in {"1","true","yes"}
        known_uids: set[str] = set()
        known_names: set[str] = set()
        with backend.db_session() as db:
            for card in db.execute("SELECT uid,name FROM cards").fetchall():
                if card["uid"]: known_uids.add(str(card["uid"]))
                if card["name"]: known_names.add(str(card["name"]))
        for row in rows:
            item=dict(row)
            item=mask_telegram_event(item,known_uids,known_names,include_name)
            output.append(item)
        return output
    return {
        "status": status, "alerts": alerts, "snapshot": snapshot,
        "event_evidence": event_evidence, "discover_events": discover_events,
        "due_items": due_items,
    }
