import json
import sqlite3

from backend.app.services.incident_event_store import IncidentEventStore


def _db():
    db = sqlite3.connect(':memory:')
    db.row_factory = sqlite3.Row
    db.executescript('''
        CREATE TABLE incidents (incident_id TEXT PRIMARY KEY, event_count INTEGER, updated_at TEXT);
        CREATE TABLE incident_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT, incident_id TEXT, source_event_id TEXT UNIQUE,
            event_type TEXT, track_id INTEGER, event_at TEXT, details_json TEXT
        );
        CREATE TABLE security_events (id INTEGER PRIMARY KEY, source_event_id TEXT UNIQUE, details_json TEXT);
        INSERT INTO incidents VALUES ('inc-1', 0, '');
        INSERT INTO security_events VALUES (1, 'src-1', '{"zone":"A"}');
    ''')
    return db


def test_record_event_persists_and_increments_count():
    db = _db()
    store = IncidentEventStore(lambda: '2026-11-12T10:00:00', 3)
    store.record_event(db, 'inc-1', {'type': 'intrusion', 'track_id': 7,
                                    'event_at': '2026-11-12T10:00:00'}, 'src-1')
    row = db.execute('SELECT * FROM incident_events').fetchone()
    assert row['source_event_id'] == 'src-1'
    assert row['track_id'] == 7
    assert db.execute("SELECT event_count FROM incidents WHERE incident_id='inc-1'").fetchone()[0] == 1


def test_record_event_respects_cooldown():
    db = _db()
    store = IncidentEventStore(lambda: '2026-11-12T10:00:02', 3)
    store.record_event(db, 'inc-1', {'type': 'intrusion', 'track_id': 7,
                                    'event_at': '2026-11-12T10:00:00'}, 'src-1')
    store.record_event(db, 'inc-1', {'type': 'intrusion', 'track_id': 7,
                                    'event_at': '2026-11-12T10:00:02'}, 'src-2')
    assert db.execute('SELECT COUNT(*) FROM incident_events').fetchone()[0] == 1
    assert db.execute("SELECT event_count FROM incidents WHERE incident_id='inc-1'").fetchone()[0] == 1


def test_link_event_preserves_details_and_adds_incident_id():
    db = _db()
    store = IncidentEventStore(lambda: '2026-11-12T10:00:00', 3)
    store.link_event(db, 'src-1', 'inc-1')
    details = json.loads(db.execute('SELECT details_json FROM security_events WHERE source_event_id=?',
                                    ('src-1',)).fetchone()[0])
    assert details == {'zone': 'A', 'incident_id': 'inc-1'}


def test_link_event_missing_source_is_noop():
    db = _db()
    IncidentEventStore(lambda: '2026-11-12T10:00:00', 3).link_event(db, 'missing', 'inc-1')
    assert db.execute('SELECT details_json FROM security_events').fetchone()[0] == '{"zone":"A"}'
