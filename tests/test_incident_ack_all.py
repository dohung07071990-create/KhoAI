import sqlite3
import time
from contextlib import contextmanager


def test_ack_all_only_acknowledges_open_unacknowledged_and_is_idempotent(monkeypatch):
    from backend.app import main

    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.execute("""CREATE TABLE incidents (
        incident_id TEXT PRIMARY KEY, status TEXT, acknowledged INTEGER,
        acknowledged_at TEXT, updated_at TEXT, incident_type TEXT,
        closed_at TEXT, siren_until REAL, event_count INTEGER,
        started_at TEXT, summary_json TEXT, session_id TEXT
    )""")
    rows = [
        ("open-1", "OPEN", 0, "intrusion"),
        ("open-2", "OPEN", 0, "intrusion"),
        ("open-active", "OPEN", 0, "intrusion"),
        ("already-acked", "OPEN", 1, "intrusion"),
        ("closed", "CLOSED", 0, "intrusion"),
    ]
    for incident_id, status, acknowledged, incident_type in rows:
        db.execute("INSERT INTO incidents (incident_id,status,acknowledged,incident_type) VALUES (?,?,?,?)",
                   (incident_id, status, acknowledged, incident_type))
    db.execute("UPDATE incidents SET siren_until=? WHERE status='OPEN'", (time.time() + 60.0,))
    db.commit()

    @contextmanager
    def fake_db_session():
        yield db

    monkeypatch.setattr(main, "db_session", fake_db_session)
    monkeypatch.setattr(main, "_current_detector_state", lambda: "ALARM")
    first = main.acknowledge_all_incidents()
    assert first["acknowledged_count"] == 3
    assert first["siren"] is True
    assert all(item["status"] == "OPEN" and item["siren"] is True
               for item in first["incidents"])
    statuses = {row["incident_id"]: (row["status"], row["acknowledged"])
                for row in db.execute("SELECT * FROM incidents")}
    assert statuses["open-1"] == ("OPEN", 1)
    assert statuses["open-2"] == ("OPEN", 1)
    assert statuses["open-active"] == ("OPEN", 1)
    assert statuses["already-acked"] == ("OPEN", 1)
    assert statuses["closed"] == ("CLOSED", 0)

    second = main.acknowledge_all_incidents()
    assert second["acknowledged_count"] == 0
    assert {row["incident_id"]: (row["status"], row["acknowledged"])
            for row in db.execute("SELECT * FROM incidents")} == statuses
    db.close()


def test_ack_all_with_no_incidents_returns_zero(monkeypatch):
    from backend.app import main

    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.execute("""CREATE TABLE incidents (
        incident_id TEXT PRIMARY KEY, status TEXT, acknowledged INTEGER,
        acknowledged_at TEXT, updated_at TEXT, incident_type TEXT,
        closed_at TEXT, siren_until REAL, event_count INTEGER,
        started_at TEXT, summary_json TEXT, session_id TEXT
    )""")

    @contextmanager
    def fake_db_session():
        yield db

    monkeypatch.setattr(main, "db_session", fake_db_session)
    monkeypatch.setattr(main, "_current_detector_state", lambda: "SAFE")
    result = main.acknowledge_all_incidents()
    assert result["acknowledged_count"] == 0
    db.close()


def test_ack_does_not_silence_siren_before_its_own_timeout(monkeypatch):
    from backend.app import main
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.execute("""CREATE TABLE incidents (
        incident_id TEXT PRIMARY KEY, status TEXT, acknowledged INTEGER,
        acknowledged_at TEXT, updated_at TEXT, incident_type TEXT,
        closed_at TEXT, siren_until REAL, event_count INTEGER,
        started_at TEXT, summary_json TEXT, session_id TEXT
    )""")
    db.execute("INSERT INTO incidents (incident_id,status,acknowledged,incident_type,siren_until) VALUES ('active','OPEN',0,'intrusion',100.0)")
    @contextmanager
    def fake_db_session():
        yield db
    monkeypatch.setattr(main, "db_session", fake_db_session)
    monkeypatch.setattr(main, "_current_detector_state", lambda: "ALARM")
    monkeypatch.setattr(main.time, "time", lambda: 99.0)
    ack = main.acknowledge_all_incidents()
    assert ack["acknowledged"] is True and ack["siren"] is True
    monkeypatch.setattr(main.time, "time", lambda: 101.0)
    expired = main._incident_status()
    assert expired["acknowledged"] is True and expired["siren"] is False
    assert expired["incidents"][0]["status"] == "OPEN"
    db.close()


def test_silence_siren_is_separate_from_ack_and_incident_state(monkeypatch):
    from backend.app import main
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.execute("""CREATE TABLE incidents (
        incident_id TEXT PRIMARY KEY, status TEXT, acknowledged INTEGER,
        acknowledged_at TEXT, updated_at TEXT, incident_type TEXT,
        closed_at TEXT, siren_until REAL, event_count INTEGER,
        started_at TEXT, summary_json TEXT, session_id TEXT
    )""")
    db.execute("INSERT INTO incidents (incident_id,status,acknowledged,incident_type,siren_until) VALUES ('active','OPEN',0,'intrusion',100.0)")
    @contextmanager
    def fake_db_session():
        yield db
    monkeypatch.setattr(main, "db_session", fake_db_session)
    monkeypatch.setattr(main, "_current_detector_state", lambda: "ALARM")
    monkeypatch.setattr(main.time, "time", lambda: 99.0)
    result = main.silence_incident_sirens()
    row = db.execute("SELECT status,acknowledged,siren_until FROM incidents WHERE incident_id='active'").fetchone()
    assert result["stopped_count"] == 1
    assert result["siren"] is False
    assert tuple(row) == ("OPEN", 0, 0.0)
    db.close()
