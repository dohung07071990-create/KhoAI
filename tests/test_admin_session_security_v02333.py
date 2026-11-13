"""Regression tests for role authorization and hashed admin sessions."""
import asyncio
import hashlib
import sqlite3

import pytest
from fastapi.testclient import TestClient

from backend.app import main as api


@pytest.fixture
def security_client(tmp_path, monkeypatch):
    monkeypatch.setattr(api, "DB_PATH", tmp_path / "security.sqlite3")
    monkeypatch.setattr(api, "CAMERA_AUTOSTART", False)

    async def idle_event_worker():
        await asyncio.sleep(3600)

    monkeypatch.setattr(api, "_camera_event_sync_worker", idle_event_worker)
    monkeypatch.setenv("KHOAI_ADMIN_TOKEN", "")
    monkeypatch.setenv("KHOAI_BOOTSTRAP_ADMIN_USERNAME", "rootadmin")
    monkeypatch.setenv("KHOAI_BOOTSTRAP_ADMIN_PASSWORD", "example-password-for-tests-01")
    with api._auth_lock:
        api._auth_failures.clear()
    api.init_db()
    with TestClient(api.app) as client:
        yield client


def _login(client, username="rootadmin", password="example-password-for-tests-01"):
    return client.post("/api/auth/login", json={"username": username, "password": password})


def _create_user(client, username, role):
    response = client.post("/api/admin/users", json={
        "username": username,
        "display_name": username.title(),
        "password": "Anotherexample-password-for-tests-01",
        "role": role,
    })
    assert response.status_code == 200, response.text
    return response.json()["user_id"]


def test_viewer_cannot_read_system_history_or_user_directory_but_can_read_operations(security_client):
    admin = security_client
    assert _login(admin).status_code == 200
    _create_user(admin, "readonly", "viewer")
    admin.post("/api/logout")
    assert _login(admin, "readonly", "Anotherexample-password-for-tests-01").status_code == 200

    assert admin.get("/api/history/advanced?kind=security").status_code == 200
    assert admin.get("/api/history/advanced?kind=access").status_code == 200
    assert admin.get("/api/history/advanced?kind=system").status_code == 403
    assert admin.get("/api/system/access-logs").status_code == 403
    assert admin.get("/api/admin/users").status_code == 403
    assert admin.post("/api/incidents/ack-all", json={}).status_code == 403


def test_session_cookie_is_hashed_in_database_and_never_returned_in_system_history(security_client):
    client = security_client
    assert _login(client).status_code == 200
    raw_cookie = client.cookies.get("khoai_admin_session")
    assert raw_cookie
    expected_digest = hashlib.sha256(raw_cookie.encode("utf-8")).hexdigest()
    with api.db_session() as db:
        stored = db.execute("SELECT session_id FROM admin_sessions").fetchone()["session_id"]
        log_values = [row[0] for row in db.execute("SELECT session_id FROM system_access_logs WHERE session_id IS NOT NULL").fetchall()]
    assert stored == expected_digest
    assert raw_cookie not in log_values
    assert all(value != raw_cookie for value in log_values)

    history = client.get("/api/history/advanced?kind=system")
    assert history.status_code == 200
    assert all("session_id" not in item for item in history.json())
    access_logs = client.get("/api/system/access-logs")
    assert access_logs.status_code == 200
    assert all("session_id" not in item for item in access_logs.json())


def test_role_demotion_revokes_existing_session_immediately(security_client):
    admin = security_client
    assert _login(admin).status_code == 200
    target_id = _create_user(admin, "secondadmin", "admin")

    other = TestClient(api.app)
    try:
        assert _login(other, "secondadmin", "Anotherexample-password-for-tests-01").status_code == 200
        assert other.get("/api/admin/users").status_code == 200
        changed = admin.patch(f"/api/admin/users/{target_id}", json={"role": "viewer"})
        assert changed.status_code == 200
        assert other.get("/api/admin/users").status_code == 401
        assert other.post("/api/incidents/ack-all", json={}).status_code == 401
        assert other.get("/api/history/advanced?kind=security").status_code == 401
    finally:
        other.close()


def test_password_change_revokes_existing_session(security_client):
    admin = security_client
    assert _login(admin).status_code == 200
    target_id = _create_user(admin, "passworduser", "admin")
    other = TestClient(api.app)
    try:
        assert _login(other, "passworduser", "Anotherexample-password-for-tests-01").status_code == 200
        changed = admin.patch(f"/api/admin/users/{target_id}", json={"password": "example-password-for-tests-03"})
        assert changed.status_code == 200
        assert other.get("/api/admin/users").status_code == 401
        assert _login(other, "passworduser", "example-password-for-tests-03").status_code == 200
    finally:
        other.close()


def test_security_migration_clears_legacy_raw_session_values(security_client):
    with api.db_session() as db:
        db.execute("DELETE FROM khoai_schema_migrations WHERE migration_id=?", ("2026-11-11_session_digest_v1",))
        db.execute("INSERT INTO admin_sessions(session_id,created_at,expires_at,operator_name,user_id,role) VALUES(?,?,?,?,NULL,'admin')",
                   ("legacy-raw-session-cookie", 1.0, 9999999999.0, "Legacy"))
        db.execute("INSERT INTO system_access_logs(event_at,event_type,operator_name,session_id,details) VALUES(?,?,?,?,?)",
                   (api.now_business(), "LOGIN", "Legacy", "legacy-raw-session-cookie", "legacy"))
    api.init_db()
    with api.db_session() as db:
        assert db.execute("SELECT COUNT(*) FROM admin_sessions").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM system_access_logs WHERE session_id IS NOT NULL").fetchone()[0] == 0


def test_session_database_error_fails_closed_as_503(security_client, monkeypatch):
    client = security_client
    assert _login(client).status_code == 200
    original = api.db_session

    class BrokenContext:
        def __enter__(self):
            raise sqlite3.OperationalError("simulated database outage")
        def __exit__(self, *args):
            return False

    monkeypatch.setattr(api, "db_session", lambda: BrokenContext())
    response = client.get("/api/admin/users")
    assert response.status_code == 503
    monkeypatch.setattr(api, "db_session", original)
