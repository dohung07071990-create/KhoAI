import sqlite3
from contextlib import contextmanager

from backend.app.services.incident_commands import IncidentCommandService


def _database():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.execute("""CREATE TABLE incidents (
        incident_id TEXT PRIMARY KEY, status TEXT, acknowledged INTEGER,
        acknowledged_at TEXT, updated_at TEXT, siren_until REAL
    )""")
    db.executemany(
        "INSERT INTO incidents VALUES(?,?,?,?,?,?)",
        [
            ("open-unacked", "OPEN", 0, None, None, 50.0),
            ("open-acked", "OPEN", 1, "old", "old", 25.0),
            ("closed", "CLOSED", 0, None, None, 50.0),
        ],
    )
    db.commit()
    return db


def test_incident_commands_preserve_ack_and_siren_separation():
    db = _database()

    @contextmanager
    def session():
        yield db

    close_calls = []
    service = IncidentCommandService(
        db_session=session,
        now_business=lambda: "2026-11-12T10:00:00",
        close_incident_if_resolved=lambda connection: close_calls.append(connection),
        incident_status=lambda: {"status": "ok"},
    )

    ack = service.acknowledge_all()
    assert ack == {"ok": True, "acknowledged_count": 1, "status": "ok"}
    assert len(close_calls) == 1
    row = db.execute("SELECT acknowledged, siren_until FROM incidents WHERE incident_id='open-unacked'").fetchone()
    assert tuple(row) == (1, 50.0)

    silenced = service.silence_sirens()
    assert silenced == {"ok": True, "stopped_count": 2, "status": "ok"}
    row = db.execute("SELECT status, acknowledged, siren_until FROM incidents WHERE incident_id='open-unacked'").fetchone()
    assert tuple(row) == ("OPEN", 1, 0.0)
    closed = db.execute("SELECT siren_until FROM incidents WHERE incident_id='closed'").fetchone()
    assert closed[0] == 50.0
    db.close()
