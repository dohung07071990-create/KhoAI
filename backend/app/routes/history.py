"""Authenticated history and dashboard summary endpoints."""
from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any, Protocol

from fastapi import APIRouter, Depends, HTTPException, Query, Request


class HistoryRouteServices(Protocol):
    db_session: Callable[[], Any]
    business_date: Callable[[], str]
    mask_uid_payload: Callable[[Any], Any]
    require_session: Callable[..., Any]


def create_history_router(services: HistoryRouteServices) -> APIRouter:
    router = APIRouter()

    @router.get("/api/history/advanced", dependencies=[Depends(services.require_session)])
    def advanced_history(
        request: Request,
        kind: str = Query("security", pattern="^(security|access|system)$"),
        q: str = Query("", max_length=100),
        start: str = Query("", max_length=30),
        end: str = Query("", max_length=30),
        limit: int = Query(200, ge=1, le=1000),
    ) -> list[dict[str, Any]]:
        if kind == "system" and getattr(request.state, "khoai_role", None) != "admin":
            raise HTTPException(status_code=403, detail="Nhật ký hệ thống chỉ dành cho admin.")
        table = {"security": "security_events", "access": "access_logs", "system": "system_access_logs"}[kind]
        clauses: list[str] = []
        params: list[Any] = []
        if start:
            clauses.append("event_at>=?")
            params.append(start)
        if end:
            clauses.append("event_at<=?")
            params.append(end + "T23:59:59" if len(end) == 10 else end)
        if q:
            fields = {
                "security": "event_type LIKE ? OR message LIKE ? OR CAST(track_id AS TEXT) LIKE ?",
                "access": "uid LIKE ? OR card_name LIKE ? OR result LIKE ?",
                "system": "operator_name LIKE ? OR event_type LIKE ? OR path LIKE ? OR details LIKE ?",
            }[kind]
            clauses.append("(" + fields + ")")
            params.extend([f"%{q}%"] * fields.count("?"))
        columns = {
            "security": "id,event_at,event_type,track_id,severity,message,details_json,source_event_id",
            "access": "id,uid,card_name,event_at,result",
            "system": "id,event_at,event_type,operator_name,ip_address,user_agent,method,path,details",
        }[kind]
        sql = f"SELECT {columns} FROM {table}"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY event_at DESC LIMIT ?"
        params.append(limit)
        with services.db_session() as db:
            rows = db.execute(sql, params).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            if "details_json" in item:
                try:
                    item["details"] = json.loads(item.pop("details_json") or "{}")
                except (TypeError, ValueError):
                    item["details"] = {}
            result.append(item)
        if getattr(request.state, "khoai_role", None) != "admin":
            result = services.mask_uid_payload(result)
        return result

    @router.get("/api/logs", dependencies=[Depends(services.require_session)])
    def list_logs(
        request: Request,
        limit: int = Query(default=100, ge=1, le=500),
    ) -> list[dict[str, Any]]:
        with services.db_session() as db:
            rows = db.execute(
                "SELECT id, uid, card_name, event_at, result FROM access_logs ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        records = [dict(row) for row in rows]
        if getattr(request.state, "khoai_role", None) != "admin":
            records = services.mask_uid_payload(records)
        return records

    @router.get("/api/stats", dependencies=[Depends(services.require_session)])
    def stats() -> dict[str, int]:
        today = services.business_date()
        with services.db_session() as db:
            cards = db.execute("SELECT COUNT(*) FROM cards WHERE active = 1").fetchone()[0]
            scans = db.execute(
                "SELECT COUNT(*) FROM access_logs WHERE substr(event_at, 1, 10) = ?", (today,)
            ).fetchone()[0]
            denied = db.execute(
                "SELECT COUNT(*) FROM access_logs WHERE substr(event_at, 1, 10) = ? AND result = 'deny'",
                (today,),
            ).fetchone()[0]
            alerts = db.execute(
                "SELECT COUNT(*) FROM security_events WHERE substr(event_at, 1, 10) = ? AND severity IN ('warning','severe')",
                (today,),
            ).fetchone()[0]
        return {"active_cards": cards, "scans_today": scans, "denied_today": denied, "alerts_today": alerts}

    return router
