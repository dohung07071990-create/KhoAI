import sqlite3

from backend.app.services.incident_health_policy import IncidentHealthPolicy


def test_classifies_camera_faults_and_ai_health():
    assert IncidentHealthPolicy.incident_type(event_type="camera_offline") == "camera_outage"
    assert IncidentHealthPolicy.incident_type(event_type="camera_unstable") == "camera_outage"
    assert IncidentHealthPolicy.incident_type(health_reason="camera_unstable") == "camera_outage"
    assert IncidentHealthPolicy.incident_type(health_reason="ai_processing_stalled") == "ai_health"
    assert IncidentHealthPolicy.incident_type() == "ai_health"


def test_camera_recovered_closes_only_camera_outage():
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE incidents(status TEXT, incident_type TEXT, closed_at TEXT, updated_at TEXT)")
    db.executemany("INSERT INTO incidents VALUES('OPEN', ?, NULL, NULL)",
                   [("camera_outage",), ("ai_health",), ("intrusion",)])
    policy = IncidentHealthPolicy(lambda: "2026-11-12T10:00:00")

    policy.close_recovered(db, {"type": "camera_recovered", "event_at": "2026-11-12T09:59:00"})

    rows = db.execute("SELECT incident_type,status,closed_at,updated_at FROM incidents ORDER BY incident_type").fetchall()
    assert rows == [
        ("ai_health", "OPEN", None, None),
        ("camera_outage", "CLOSED", "2026-11-12T09:59:00", "2026-11-12T10:00:00"),
        ("intrusion", "OPEN", None, None),
    ]


def test_non_camera_health_recovery_closes_camera_and_ai_health_only():
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE incidents(status TEXT, incident_type TEXT, closed_at TEXT, updated_at TEXT)")
    db.executemany("INSERT INTO incidents VALUES('OPEN', ?, NULL, NULL)",
                   [("camera_outage",), ("ai_health",), ("intrusion",)])
    policy = IncidentHealthPolicy(lambda: "2026-11-12T10:00:00")

    policy.close_recovered(db, {"type": "ai_recovered"})

    rows = db.execute("SELECT incident_type,status,closed_at,updated_at FROM incidents ORDER BY incident_type").fetchall()
    assert rows == [
        ("ai_health", "CLOSED", "2026-11-12T10:00:00", "2026-11-12T10:00:00"),
        ("camera_outage", "CLOSED", "2026-11-12T10:00:00", "2026-11-12T10:00:00"),
        ("intrusion", "OPEN", None, None),
    ]
