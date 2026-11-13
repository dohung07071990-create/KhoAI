import asyncio
import pytest
from fastapi.testclient import TestClient
from backend.app import main as api


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(api, "DB_PATH", tmp_path / "accounts.sqlite3")
    monkeypatch.setattr(api, "CAMERA_AUTOSTART", False)
    # These tests exercise API behavior directly; do not start the independent
    # periodic detector-event writer against the fixture database.
    async def idle_event_worker():
        await asyncio.sleep(3600)
    monkeypatch.setattr(api, "_camera_event_sync_worker", idle_event_worker)
    monkeypatch.setenv("KHOAI_ADMIN_TOKEN", "")
    monkeypatch.setenv("KHOAI_BOOTSTRAP_ADMIN_USERNAME", "rootadmin")
    monkeypatch.setenv("KHOAI_BOOTSTRAP_ADMIN_PASSWORD", "StrongPassword_2026!")
    with api._auth_lock:
        api._auth_failures.clear()
    api.init_db()
    with TestClient(api.app) as test_client:
        yield test_client


def test_bootstrap_account_login_and_session(client):
    response = client.post("/api/auth/login", json={"username": "rootadmin", "password": "StrongPassword_2026!"})
    assert response.status_code == 200
    assert response.json()["role"] == "admin"
    assert client.get("/api/auth/me").status_code == 200
    assert client.get("/api/admin/users").status_code == 200


def test_wrong_password_is_rejected(client):
    response = client.post("/api/auth/login", json={"username": "rootadmin", "password": "wrong-password"})
    assert response.status_code == 401


def test_viewer_cannot_mutate(client):
    assert client.post("/api/auth/login", json={"username": "rootadmin", "password": "StrongPassword_2026!"}).status_code == 200
    created = client.post("/api/admin/users", json={
        "username": "readonly", "display_name": "Người xem", "password": "ViewerPassword_2026!", "role": "viewer"
    })
    assert created.status_code == 200
    client.post("/api/logout")
    assert client.post("/api/auth/login", json={"username": "readonly", "password": "ViewerPassword_2026!"}).status_code == 200
    assert client.get("/api/admin/users").status_code == 403
    assert client.get("/api/history/advanced?kind=security").status_code == 200
    assert client.get("/api/history/advanced?kind=system").status_code == 403
    denied = client.post("/api/incidents/ack-all", json={})
    assert denied.status_code == 403


def test_explainability_and_camera_center_api_shape(client):
    assert client.post("/api/auth/login", json={"username": "rootadmin", "password": "StrongPassword_2026!"}).status_code == 200
    # Detector may be unavailable in a test container; APIs must still return explicit, non-fabricated status.
    explain = client.get("/api/ai/explainability")
    center = client.get("/api/cameras/center")
    assert explain.status_code == 200
    assert "state" in explain.json() and "inputs" in explain.json()
    assert center.status_code == 200
    assert center.json()["internal"]["ai_enabled"] is False


def test_disabling_user_revokes_their_existing_session(client):
    assert client.post("/api/auth/login", json={"username": "rootadmin", "password": "StrongPassword_2026!"}).status_code == 200
    created = client.post("/api/admin/users", json={
        "username": "temporary", "display_name": "Tài khoản tạm", "password": "TemporaryPassword_2026!", "role": "admin"
    })
    user_id = created.json()["user_id"]
    client.post("/api/logout")
    assert client.post("/api/auth/login", json={"username": "temporary", "password": "TemporaryPassword_2026!"}).status_code == 200
    client.post("/api/logout")
    assert client.post("/api/auth/login", json={"username": "rootadmin", "password": "StrongPassword_2026!"}).status_code == 200
    assert client.patch(f"/api/admin/users/{user_id}", json={"active": False}).status_code == 200
    client.post("/api/logout")
    assert client.post("/api/auth/login", json={"username": "temporary", "password": "TemporaryPassword_2026!"}).status_code == 401
