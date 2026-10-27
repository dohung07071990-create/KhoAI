"""Server kho thông minh - FastAPI + SQLite.
Chạy:  cd server && pip install -r requirements.txt && uvicorn main:app --host 0.0.0.0 --port 8000
Server là nơi QUYẾT ĐỊNH báo động. ESP32 và camera AI chỉ gửi số liệu."""
import sqlite3
from datetime import datetime, date
from typing import List, Optional
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# ====== CẤU HÌNH (đổi ở một chỗ) ======
TIME_SCALE = 60            # 1 giây demo = 60 giây ngoài đời
WARN_REAL_MIN = 10         # đứng lâu >= 10 phút ngoài đời -> warning
SEVERE_REAL_MIN = 20       # >= 20 phút -> severe
DB_FILE = "kho.db"
ZONES = ["entry", "exit", "important", "critical"]   # Nhập, Xuất, Quan trọng, Cực kỳ quan trọng
CRITICAL_ZONES = {"important", "critical"}
HEARTBEAT_TIMEOUT = 15     # giây không có heartbeat -> ngoại tuyến

app = FastAPI(title="Kho thông minh")
state = {"outside": {"people": 0, "max_seconds": 0, "ts": None}, "inside": []}


def now():
    return datetime.now().isoformat(timespec="seconds")


def q(sql, args=(), one=False, commit=False):
    c = sqlite3.connect(DB_FILE)
    c.row_factory = sqlite3.Row
    try:
        cur = c.execute(sql, args)
        if commit:
            c.commit()
            return cur.lastrowid
        rows = [dict(r) for r in cur.fetchall()]
    finally:
        c.close()
    return (rows[0] if rows else None) if one else rows


@app.on_event("startup")
def init():
    c = sqlite3.connect(DB_FILE)
    c.executescript("""
    CREATE TABLE IF NOT EXISTS cards(
      uid TEXT PRIMARY KEY, name TEXT NOT NULL, age INTEGER,
      expires_at TEXT, daily_quota INTEGER DEFAULT 3, used_today INTEGER DEFAULT 0,
      last_reset_date TEXT, color TEXT);
    CREATE TABLE IF NOT EXISTS scans(
      id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, uid TEXT, name TEXT,
      result TEXT, reason TEXT, device_id TEXT);
    CREATE TABLE IF NOT EXISTS permissions(uid TEXT, zone TEXT, PRIMARY KEY(uid, zone));
    CREATE TABLE IF NOT EXISTS pickup_orders(
      id INTEGER PRIMARY KEY AUTOINCREMENT, uid TEXT, item TEXT, boxes INTEGER, zone TEXT, day TEXT);
    CREATE TABLE IF NOT EXISTS alerts(
      id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, level TEXT, kind TEXT, zone TEXT,
      message TEXT, uid TEXT, handled INTEGER DEFAULT 0);
    CREATE TABLE IF NOT EXISTS devices(
      device_id TEXT PRIMARY KEY, last_seen TEXT, alarm TEXT DEFAULT 'off');
    """)
    c.commit()
    c.close()


class Scan(BaseModel):
    uid: str
    device_id: str = "esp32-door"


class Heartbeat(BaseModel):
    device_id: str = "esp32-door"


class CardIn(BaseModel):
    uid: str
    name: str
    age: Optional[int] = None
    expires_at: Optional[str] = None       # YYYY-MM-DD
    daily_quota: int = 3
    zones: List[str] = []
    color: Optional[str] = None
    item: Optional[str] = None             # loại hàng được lấy
    boxes: int = 0                         # số thùng được lấy


class Person(BaseModel):
    color: Optional[str] = None
    zone: str
    seconds: float = 0


class Event(BaseModel):
    camera: str                            # "outside" | "inside"
    people_in_zone: int = 0                # camera ngoài: số người trong vùng A
    max_seconds: float = 0                 # camera ngoài: giây đứng lâu nhất (thời gian demo)
    people: List[Person] = []              # camera trong
    boxes: int = 0                         # số thùng đếm được


def raise_alert(level, kind, zone, message, uid=None):
    if q("SELECT id FROM alerts WHERE handled=0 AND kind=? AND zone IS ? AND uid IS ?", (kind, zone, uid), one=True):
        return
    q("INSERT INTO alerts(ts,level,kind,zone,message,uid) VALUES(?,?,?,?,?,?)",
      (now(), level, kind, zone, message, uid), commit=True)


def current_alarm():
    levels = {r["level"] for r in q("SELECT level FROM alerts WHERE handled=0")}
    return "severe" if "severe" in levels else "warning" if "warning" in levels else "off"


def scans_today_ok():
    return q("SELECT COUNT(DISTINCT uid) n FROM scans WHERE result='allow' AND ts>=?",
             (date.today().isoformat(),), one=True)["n"]


# ====== RFID ======
@app.post("/api/rfid/scan")
def rfid_scan(s: Scan):
    uid, today = s.uid.strip().upper(), date.today().isoformat()
    card = q("SELECT * FROM cards WHERE uid=?", (uid,), one=True)
    name, reason = None, None
    if not card:
        reason = "unknown_card"
    else:
        name = card["name"]
        if card["last_reset_date"] != today:          # reset hạn mức lúc 0h
            q("UPDATE cards SET used_today=0,last_reset_date=? WHERE uid=?", (today, uid), commit=True)
            card["used_today"] = 0
        if card["expires_at"] and card["expires_at"] < today:
            reason = "expired"
        elif card["used_today"] >= card["daily_quota"]:
            reason = "quota_exhausted"
    allow = reason is None
    if allow:
        q("UPDATE cards SET used_today=used_today+1 WHERE uid=?", (uid,), commit=True)
    else:
        raise_alert("warning", reason, "door", f"Quẹt thẻ bị từ chối ({reason}): {name or uid}", uid)
    q("INSERT INTO scans(ts,uid,name,result,reason,device_id) VALUES(?,?,?,?,?,?)",
      (now(), uid, name, "allow" if allow else "deny", reason, s.device_id), commit=True)
    return {"allow": allow, "reason": reason, "name": name, "alarm": current_alarm()}


@app.get("/api/rfid/last-unknown")
def last_unknown():
    return q("SELECT uid, ts FROM scans WHERE reason='unknown_card' ORDER BY id DESC LIMIT 1", one=True) \
        or {"uid": None, "ts": None}


@app.post("/api/device/heartbeat")
def heartbeat(h: Heartbeat):
    alarm = current_alarm()
    q("INSERT INTO devices(device_id,last_seen,alarm) VALUES(?,?,?) "
      "ON CONFLICT(device_id) DO UPDATE SET last_seen=excluded.last_seen, alarm=excluded.alarm",
      (h.device_id, now(), alarm), commit=True)
    return {"alarm": alarm}


# ====== THẺ ======
@app.get("/api/cards")
def list_cards():
    cards = q("SELECT * FROM cards ORDER BY name")
    for c in cards:
        c["zones"] = [p["zone"] for p in q("SELECT zone FROM permissions WHERE uid=?", (c["uid"],))]
        o = q("SELECT item,boxes FROM pickup_orders WHERE uid=? ORDER BY id DESC LIMIT 1", (c["uid"],), one=True)
        c["item"], c["boxes"] = (o["item"], o["boxes"]) if o else (None, 0)
    return cards


@app.post("/api/cards")
def create_card(c: CardIn):
    uid, today = c.uid.strip().upper(), date.today().isoformat()
    if not uid or not c.name.strip():
        raise HTTPException(400, "Cần UID và tên")
    if any(z not in ZONES for z in c.zones):
        raise HTTPException(400, "Vùng không hợp lệ")
    if c.color and q("SELECT 1 FROM cards WHERE color=? AND uid!=? AND (expires_at IS NULL OR expires_at>=?)",
                     (c.color, uid, today), one=True):
        raise HTTPException(409, "Màu này đã gán cho thẻ khác còn hiệu lực")
    q("INSERT OR REPLACE INTO cards(uid,name,age,expires_at,daily_quota,used_today,last_reset_date,color) "
      "VALUES(?,?,?,?,?,0,?,?)",
      (uid, c.name.strip(), c.age, c.expires_at or None, c.daily_quota, today, c.color or None), commit=True)
    q("DELETE FROM permissions WHERE uid=?", (uid,), commit=True)
    for z in c.zones:
        q("INSERT INTO permissions(uid,zone) VALUES(?,?)", (uid, z), commit=True)
    if c.item and c.boxes:
        q("INSERT INTO pickup_orders(uid,item,boxes,zone,day) VALUES(?,?,?,?,?)",
          (uid, c.item, c.boxes, c.zones[0] if c.zones else None, today), commit=True)
    return {"ok": True}


@app.delete("/api/cards/{uid}")
def delete_card(uid: str):
    for t in ("cards", "permissions", "pickup_orders"):
        q(f"DELETE FROM {t} WHERE uid=?", (uid.upper(),), commit=True)
    return {"ok": True}


# ====== LỊCH SỬ, CẢNH BÁO, TRẠNG THÁI ======
@app.get("/api/scans")
def list_scans(limit: int = 100):
    return q("SELECT * FROM scans ORDER BY id DESC LIMIT ?", (limit,))


@app.get("/api/alerts")
def list_alerts():
    return q("SELECT * FROM alerts ORDER BY handled, id DESC LIMIT 100")


@app.post("/api/alerts/{aid}/ack")
def ack(aid: int):
    q("UPDATE alerts SET handled=1 WHERE id=?", (aid,), commit=True)
    return {"ok": True, "alarm": current_alarm()}


@app.get("/api/status")
def status():
    d = q("SELECT * FROM devices ORDER BY last_seen DESC LIMIT 1", one=True)
    online = bool(d and (datetime.now() - datetime.fromisoformat(d["last_seen"])).total_seconds() < HEARTBEAT_TIMEOUT)
    out = dict(state["outside"])
    out["scanned"] = scans_today_ok()
    out["real_minutes"] = round(out["max_seconds"] * TIME_SCALE / 60, 1)
    return {
        "device_online": online, "alarm": current_alarm(), "time_scale": TIME_SCALE,
        "cards": q("SELECT COUNT(*) n FROM cards", one=True)["n"],
        "scans_today": q("SELECT COUNT(*) n FROM scans WHERE ts>=?", (date.today().isoformat(),), one=True)["n"],
        "open_alerts": q("SELECT COUNT(*) n FROM alerts WHERE handled=0", one=True)["n"],
        "outside": out, "inside": state["inside"],
    }


# ====== SỰ KIỆN TỪ CAMERA AI ======
@app.post("/api/events")
def events(e: Event):
    scanned, today = scans_today_ok(), date.today().isoformat()
    if e.camera == "outside":
        state["outside"] = {"people": e.people_in_zone, "max_seconds": e.max_seconds, "ts": now()}
        real_min = e.max_seconds * TIME_SCALE / 60
        if e.people_in_zone > scanned:
            raise_alert("warning", "tailgating", "A",
                        f"{e.people_in_zone} người ở vùng A nhưng chỉ {scanned} lượt quẹt hợp lệ")
        if real_min >= WARN_REAL_MIN:
            raise_alert("severe" if real_min >= SEVERE_REAL_MIN else "warning", "loitering", "A",
                        f"Đứng lâu ở vùng A ~{real_min:.0f} phút")
    else:
        view = []
        for p in e.people:
            card = q("SELECT * FROM cards WHERE color=?", (p.color,), one=True) if p.color else None
            wrong = False
            if card:
                allowed = {r["zone"] for r in q("SELECT zone FROM permissions WHERE uid=?", (card["uid"],))}
                if p.zone not in allowed:
                    wrong = True
                    raise_alert("severe" if p.zone in CRITICAL_ZONES else "warning", "wrong_zone", p.zone,
                                f"{card['name']} đứng sai vùng {p.zone}", card["uid"])
            view.append({"color": p.color, "zone": p.zone, "name": card["name"] if card else None, "wrong": wrong})
            real_min = p.seconds * TIME_SCALE / 60
            if p.zone in CRITICAL_ZONES and real_min >= WARN_REAL_MIN:
                raise_alert("severe" if real_min >= SEVERE_REAL_MIN else "warning", "loitering", p.zone,
                            f"Ở lâu trong vùng {p.zone} ~{real_min:.0f} phút")
        if len(e.people) > scanned:       # luật dự phòng: đếm số người
            raise_alert("warning", "headcount", None, f"{len(e.people)} người trong kho, {scanned} lượt quẹt hợp lệ")
        allowed_boxes = q("SELECT COALESCE(SUM(boxes),0) n FROM pickup_orders WHERE day=?", (today,), one=True)["n"]
        if e.boxes > allowed_boxes:
            raise_alert("severe", "boxes_over", None, f"Đếm {e.boxes} thùng, hồ sơ chỉ cho {allowed_boxes}")
        state["inside"] = view
    return {"ok": True, "alarm": current_alarm()}


app.mount("/", StaticFiles(directory="static", html=True), name="static")
