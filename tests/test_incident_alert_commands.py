import sqlite3
from contextlib import contextmanager
import pytest
from fastapi import HTTPException
from backend.app.services.incident_alert_commands import IncidentAlertCommandService


def test_alert_acknowledge_marks_existing_alert(tmp_path):
    path = tmp_path / 'alerts.db'
    db = sqlite3.connect(path); db.execute('CREATE TABLE security_events(id INTEGER PRIMARY KEY)'); db.execute('CREATE TABLE acknowledged_events(event_id INTEGER PRIMARY KEY, acknowledged_at TEXT)'); db.execute('INSERT INTO security_events(id) VALUES(4)'); db.commit(); db.close()
    @contextmanager
    def session():
        conn = sqlite3.connect(path)
        try: yield conn; conn.commit()
        finally: conn.close()
    service = IncidentAlertCommandService(session, lambda: 'stamp', lambda: 'warning')
    assert service.acknowledge(4) == {'ok': True, 'alarm': 'warning'}
    db = sqlite3.connect(path)
    assert db.execute('SELECT acknowledged_at FROM acknowledged_events WHERE event_id=4').fetchone()[0] == 'stamp'
    db.close()


def test_alert_acknowledge_missing_alert_returns_404(tmp_path):
    path = tmp_path / 'alerts.db'
    db = sqlite3.connect(path); db.execute('CREATE TABLE security_events(id INTEGER PRIMARY KEY)'); db.execute('CREATE TABLE acknowledged_events(event_id INTEGER PRIMARY KEY, acknowledged_at TEXT)'); db.commit(); db.close()
    @contextmanager
    def session():
        conn = sqlite3.connect(path)
        try: yield conn; conn.commit()
        finally: conn.close()
    service = IncidentAlertCommandService(session, lambda: 'stamp', lambda: 'off')
    with pytest.raises(HTTPException) as exc: service.acknowledge(999)
    assert exc.value.status_code == 404
