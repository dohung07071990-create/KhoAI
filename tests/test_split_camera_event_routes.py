import sqlite3
from contextlib import contextmanager
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.routes.camera_event_feed import create_camera_event_feed_router
from backend.app.routes.incident_timeline import create_incident_timeline_router
from backend.app.routes.camera_events import create_camera_event_router
from tests._route_utils import iter_registered_routes


def _services(path):
    @contextmanager
    def db_session():
        db = sqlite3.connect(path)
        db.row_factory = sqlite3.Row
        try:
            yield db
        finally:
            db.close()

    return SimpleNamespace(db_session=db_session, require_session=lambda: None,
                           mask_uid_payload=lambda value: value)


def test_camera_event_routes_are_split_and_compatibility_facade_keeps_paths(tmp_path):
    path = tmp_path / "camera-events.db"
    db = sqlite3.connect(path)
    db.executescript("""
        CREATE TABLE security_events(id INTEGER PRIMARY KEY, event_at TEXT, event_type TEXT,
            track_id INTEGER, severity TEXT, message TEXT, details_json TEXT, source_event_id TEXT);
        CREATE TABLE incidents(incident_id TEXT PRIMARY KEY, status TEXT);
        CREATE TABLE incident_events(id INTEGER PRIMARY KEY, incident_id TEXT, event_type TEXT,
            track_id INTEGER, event_at TEXT, details_json TEXT);
        INSERT INTO security_events VALUES(1,'2026-01-01','intrusion',7,'severe','Intrusion','{"zone":"A"}','src-1');
        INSERT INTO incidents VALUES('inc-1','OPEN');
        INSERT INTO incident_events VALUES(1,'inc-1','intrusion',7,'2026-01-01','{"reason":"zone entry"}');
    """)
    db.commit(); db.close()

    services = _services(path)
    app = FastAPI()
    app.include_router(create_camera_event_feed_router(services))
    app.include_router(create_incident_timeline_router(services))
    app.include_router(create_camera_event_router(services))
    paths = [route.path for route in iter_registered_routes(app.routes)]
    assert paths.count("/api/camera/events") == 2
    assert paths.count("/api/incidents/{incident_id}/timeline") == 2

    # Exercise the two independently registered route modules.
    isolated = FastAPI()
    isolated.include_router(create_camera_event_feed_router(services))
    isolated.include_router(create_incident_timeline_router(services))
    client = TestClient(isolated)
    feed = client.get("/api/camera/events")
    timeline = client.get("/api/incidents/inc-1/timeline")
    assert feed.status_code == 200
    assert feed.json()[0]["type"] == "intrusion"
    assert timeline.status_code == 200
    assert timeline.json()["events"][0]["explanation"] == "zone entry"
