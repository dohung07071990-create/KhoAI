import sqlite3
from contextlib import contextmanager
from datetime import datetime
from zoneinfo import ZoneInfo

from backend.app.services.access_statistics import AccessStatisticsService
from backend.app.services.external_alert_store import ExternalAlertStore


def _database():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.executescript("""
        CREATE TABLE access_logs(uid TEXT, result TEXT, event_at TEXT);
        CREATE TABLE security_events(
            id INTEGER PRIMARY KEY AUTOINCREMENT, event_at TEXT, event_type TEXT,
            track_id TEXT, severity TEXT, message TEXT, details_json TEXT
        );
        CREATE TABLE acknowledged_events(event_id INTEGER PRIMARY KEY);
    """)

    @contextmanager
    def session():
        yield db

    return db, session


def test_access_statistics_service_counts_allowed_scans():
    db, session = _database()
    tz = ZoneInfo("Asia/Ho_Chi_Minh")
    now = datetime.now(tz).isoformat(timespec="seconds")
    db.executemany(
        "INSERT INTO access_logs(uid,result,event_at) VALUES(?,?,?)",
        [("A", "allow", now), ("B", "allow", now), ("C", "deny", now)],
    )
    service = AccessStatisticsService(session, tz)
    assert service.recently_allowed(120) == 2
    assert service.today_allowed() == 2


def test_external_alert_store_suppresses_unacknowledged_duplicates():
    db, session = _database()
    store = ExternalAlertStore(session, lambda: "2026-11-12T12:00:00+07:00")
    store.persist("warning", "loitering", "A", "first", details={"seconds": 30})
    store.persist("warning", "loitering", "A", "duplicate", details={"seconds": 45})
    assert db.execute("SELECT COUNT(*) FROM security_events").fetchone()[0] == 1

    event_id = db.execute("SELECT id FROM security_events").fetchone()[0]
    db.execute("INSERT INTO acknowledged_events(event_id) VALUES(?)", (event_id,))
    store.persist("warning", "loitering", "A", "new after acknowledgement")
    assert db.execute("SELECT COUNT(*) FROM security_events").fetchone()[0] == 2
