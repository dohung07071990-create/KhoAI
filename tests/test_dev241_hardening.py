from pathlib import Path
import asyncio
import pytest
from fastapi.testclient import TestClient

from backend.app import main as api


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(api, "DB_PATH", tmp_path / "dev241.sqlite3")
    monkeypatch.setattr(api, "CAMERA_AUTOSTART", False)
    async def idle_worker():
        await asyncio.sleep(3600)
    monkeypatch.setattr(api, "_camera_event_sync_worker", idle_worker)
    monkeypatch.setenv("KHOAI_ADMIN_TOKEN", "")
    monkeypatch.setenv("KHOAI_BOOTSTRAP_ADMIN_USERNAME", "rootadmin")
    monkeypatch.setenv("KHOAI_BOOTSTRAP_ADMIN_PASSWORD", "example-password-for-tests-01")
    with api._auth_lock:
        api._auth_failures.clear()
    api.init_db()
    with TestClient(api.app) as test_client:
        yield test_client


def _login(client, username="rootadmin", password="example-password-for-tests-01"):
    return client.post("/api/auth/login", json={"username": username, "password": password})


def test_docker_image_contains_profiles_and_uses_example_zone():
    root = Path(__file__).resolve().parents[1]
    dockerfile = (root / "Dockerfile").read_text(encoding="utf-8")
    assert "COPY config ./config" in dockerfile
    assert "cp ai/zone.json.example /app/data/zone.json" in dockerfile
    assert (root / "config/profiles/demo.json").is_file()
    assert (root / "config/profiles/strict.json").is_file()


def test_device_api_rejects_sample_or_short_key(client, monkeypatch):
    monkeypatch.setenv("KHOAI_API_KEY", "test-device-key")
    response = client.post("/api/rfid/scan", json={"uid": "A1B2C3D4"}, headers={"X-API-Key": "test-device-key"})
    assert response.status_code == 503


def test_viewer_uid_is_masked_across_access_endpoints(client):
    assert _login(client).status_code == 200
    viewer_id = client.post("/api/admin/users", json={
        "username": "readonly", "display_name": "Readonly",
        "password": "Anotherexample-password-for-tests-01", "role": "viewer",
    }).json()["user_id"]
    with api.db_session() as db:
        db.execute("INSERT INTO access_logs(uid,card_name,event_at,result) VALUES(?,?,?,?)",
                   ("A1B2C3D4", "Test card", api.now_business(), "deny"))
    client.post("/api/logout")
    assert _login(client, "readonly", "Anotherexample-password-for-tests-01").status_code == 200
    for endpoint in ("/api/logs", "/api/scans", "/api/history/advanced?kind=access"):
        response = client.get(endpoint)
        assert response.status_code == 200, (endpoint, response.text)
        assert response.json()[0]["uid"] == "****C3D4"


def test_admin_cannot_disable_or_demote_self_or_last_admin(client):
    assert _login(client).status_code == 200
    with api.db_session() as db:
        admin_id = int(db.execute("SELECT user_id FROM admin_users WHERE username='rootadmin'").fetchone()[0])
    self_disable = client.patch(f"/api/admin/users/{admin_id}", json={"active": False})
    assert self_disable.status_code == 409
    self_demote = client.patch(f"/api/admin/users/{admin_id}", json={"role": "viewer"})
    assert self_demote.status_code == 409
    # Even a different admin session cannot remove the final active administrator.
    assert client.patch(f"/api/admin/users/{admin_id}", json={"active": False}).status_code == 409
