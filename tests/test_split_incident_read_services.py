import sqlite3
from contextlib import contextmanager

from backend.app.services.incident_read_service import IncidentReadService
from backend.app.services.security_alert_query_service import SecurityAlertQueryService


def _session_factory(path):
    @contextmanager
    def session():
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()
    return session


def test_incident_read_service_reads_events_and_masks_non_admin(tmp_path):
    path = tmp_path / "incident-read.db"
    db = sqlite3.connect(path)
    db.executescript("""
        CREATE TABLE incidents(incident_id TEXT, acknowledged INTEGER, incident_type TEXT,
            status TEXT, siren_until REAL, started_at TEXT);
        CREATE TABLE incident_events(id INTEGER, incident_id TEXT, event_type TEXT,
            track_id INTEGER, event_at TEXT, details_json TEXT);
        INSERT INTO incidents VALUES('i-1',0,'intrusion','OPEN',0,'2026-01-01');
        INSERT INTO incident_events VALUES(1,'i-1','intrusion',7,'2026-01-01','{"zone":"A"}');
    """)
    db.commit(); db.close()
    masked = []
    service = IncidentReadService(_session_factory(path), lambda value: masked.append(value) or value,
                                  wall_time=lambda: 10.0)
    result = service.list_incidents("operator", 10)
    assert result[0]["incident_id"] == "i-1"
    assert result[0]["events"][0]["details"] == {"zone": "A"}
    assert result[0]["acknowledged"] is False
    assert len(masked) == 1


def test_security_alert_query_service_filters_and_maps_alerts(tmp_path):
    path = tmp_path / "security-alerts.db"
    db = sqlite3.connect(path)
    db.executescript("""
        CREATE TABLE security_events(id INTEGER PRIMARY KEY, severity TEXT, event_type TEXT,
            event_at TEXT, details_json TEXT);
        CREATE TABLE acknowledged_events(event_id INTEGER PRIMARY KEY, acknowledged_at TEXT);
        INSERT INTO security_events VALUES(1,'warning','zone_warning','2026-01-01','{"zone":"A","uid":"1234"}');
        INSERT INTO security_events VALUES(2,'info','system_info','2026-01-02','{}');
        INSERT INTO acknowledged_events VALUES(1,'2026-01-03');
    """)
    db.commit(); db.close()
    masked = []
    service = SecurityAlertQueryService(_session_factory(path), lambda value: masked.append(value) or value)
    result = service.list_alerts("operator", 10, "warning")
    assert len(result) == 1
    assert result[0]["event_type"] == "zone_warning"
    assert result[0]["handled"] == 1
    assert result[0]["zone"] == "A"
    assert result[0]["uid"] == "1234"
    assert len(masked) == 1
