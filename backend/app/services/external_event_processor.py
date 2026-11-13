"""Business processing for compatibility events received from external cameras."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Callable

from ..schemas import SecurityEventInput


def process_external_camera_event(
    payload: SecurityEventInput,
    services: Any,
    persist_external_alert: Callable[..., None],
) -> dict[str, Any]:
    """Apply external-camera business rules without owning HTTP routing.

    Runtime dependencies and persistence callbacks are injected by the composition
    root/router so this service remains independent of FastAPI application state.
    """
    scanned = services.scans_recently_allowed(120)
    if payload.camera == "outside":
        state = services.external_camera_state
        if hasattr(state, "update_outside"):
            state.update_outside(payload.people_in_zone, payload.max_seconds, services.now_business())
        else:  # Backward compatibility for callers injecting the legacy dict.
            state["outside"] = {
                "people": payload.people_in_zone, "max_seconds": payload.max_seconds,
                "ts": services.now_business(),
            }
        real_minutes = payload.max_seconds * services.external_time_scale / 60
        if payload.people_in_zone > scanned:
            persist_external_alert(
                "warning", "possible_tailgating", "A",
                f"Có {payload.people_in_zone} người trong khung hình và {scanned} lượt quẹt hợp lệ trong 120 giây gần nhất; cần xác minh thủ công.",
                details={"people_in_zone": payload.people_in_zone,
                         "valid_scans_last_120s": scanned, "heuristic": True},
            )
        if real_minutes >= services.external_warn_minutes:
            level = "severe" if real_minutes >= services.external_severe_minutes else "warning"
            persist_external_alert(
                level, "loitering", "A",
                f"Phát hiện đứng lâu ở vùng A khoảng {real_minutes:.1f} phút.",
                details={"seconds": payload.max_seconds, "real_minutes": real_minutes},
            )
    elif payload.camera == "inside":
        view = []
        for person in payload.people:
            color = str(person.get("color") or "").strip()
            zone = str(person.get("zone") or "")
            seconds = float(person.get("seconds") or 0)
            with services.db_session() as db:
                card = db.execute(
                    "SELECT uid,name FROM cards WHERE upper(color)=upper(?) AND active=1 LIMIT 1",
                    (color,),
                ).fetchone() if color else None
                allowed_zones = {
                    row["zone"] for row in db.execute(
                        "SELECT zone FROM card_permissions WHERE uid=?", (card["uid"],)
                    ).fetchall()
                } if card else set()
            wrong = bool(card and zone not in allowed_zones)
            if wrong and card is not None:
                level = "severe" if zone in {"important", "critical"} else "warning"
                persist_external_alert(
                    level, "wrong_zone", zone, f"{card['name']} đứng sai vùng {zone}.",
                    card["uid"], {"color": color},
                )
            real_minutes = seconds * services.external_time_scale / 60
            if zone in {"important", "critical"} and real_minutes >= services.external_warn_minutes:
                level = "severe" if real_minutes >= services.external_severe_minutes else "warning"
                persist_external_alert(
                    level, "loitering", zone,
                    f"Có người đứng lâu trong vùng {zone} khoảng {real_minutes:.1f} phút.",
                    card["uid"] if card else None,
                    {"color": color, "real_minutes": real_minutes},
                )
            view.append({"color": color or None, "zone": zone,
                         "name": card["name"] if card else None, "wrong": wrong})
        state = services.external_camera_state
        if hasattr(state, "update_inside"):
            state.update_inside(view)
        else:  # Backward compatibility for callers injecting the legacy dict.
            state["inside"] = view
        if len(payload.people) > scanned:
            persist_external_alert(
                "warning", "headcount", None,
                f"Camera trong ghi nhận {len(payload.people)} người nhưng chỉ {scanned} lượt quẹt hợp lệ.",
                details={"people": len(payload.people), "scans_today": scanned},
            )
        today = datetime.now(services.business_tz).date().isoformat()
        with services.db_session() as db:
            allowed_boxes = int(db.execute(
                "SELECT COALESCE(SUM(boxes),0) FROM pickup_orders WHERE day=?", (today,)
            ).fetchone()[0])
        if payload.boxes > allowed_boxes:
            persist_external_alert(
                "severe", "boxes_over", None,
                f"Camera đếm {payload.boxes} thùng, hồ sơ cho phép {allowed_boxes} thùng.",
                details={"observed_boxes": payload.boxes, "authorized_boxes": allowed_boxes},
            )
    if payload.event_type or payload.message:
        severity = payload.severity if payload.severity in {
            "info", "warning", "severe", "high", "critical"
        } else "warning"
        with services.db_session() as db:
            db.execute(
                "INSERT INTO security_events(event_at,event_type,track_id,severity,message,details_json) "
                "VALUES(?,?,?,?,?,?)",
                (services.now_business(), payload.event_type or "camera_event", None, severity,
                 payload.message or "Sự kiện camera từ hệ thống ngoài.",
                 json.dumps(payload.details, ensure_ascii=False)),
            )
    return {
        "ok": True, "alarm": services.current_alarm_level(),
        "recorded": payload.camera in {"outside", "inside"} or bool(payload.event_type or payload.message),
    }
