import sqlite3
from contextlib import contextmanager
from backend.app.services.incident_query_service import IncidentQueryService


def test_query_service_lists_incidents_and_masks_non_admin(tmp_path):
    path = tmp_path / 'query.db'
    db = sqlite3.connect(path); db.row_factory = sqlite3.Row
    db.executescript('''CREATE TABLE incidents(incident_id TEXT, acknowledged INTEGER, incident_type TEXT, status TEXT, siren_until REAL, started_at TEXT);
    CREATE TABLE incident_events(id INTEGER, incident_id TEXT, event_type TEXT, track_id INTEGER, event_at TEXT, details_json TEXT);
    INSERT INTO incidents VALUES('i1',0,'intrusion','OPEN',0,'2026-01-01');
    INSERT INTO incident_events VALUES(1,'i1','intrusion',7,'2026-01-01','{"zone":"A"}');'''); db.commit(); db.close()
    @contextmanager
    def session():
        conn = sqlite3.connect(path); conn.row_factory = sqlite3.Row
        try: yield conn; conn.commit()
        finally: conn.close()
    service = IncidentQueryService(session, lambda value: value)
    rows = service.list_incidents('user', 10)
    assert rows[0]['incident_id'] == 'i1'
    assert rows[0]['events'][0]['details'] == {'zone': 'A'}
    assert rows[0]['acknowledged'] is False
