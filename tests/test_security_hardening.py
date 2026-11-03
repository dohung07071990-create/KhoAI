from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from backend.app import main


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "test.sqlite3")
    monkeypatch.setattr(main, "CAMERA_AUTOSTART", False)
    monkeypatch.setenv("KHOAI_ADMIN_TOKEN", "test-admin-token")
    monkeypatch.setenv("KHOAI_API_KEY", "test-device-key")
    main.init_db()
    with TestClient(main.app) as test_client:
        yield test_client


def test_write_routes_require_admin_token(client):
    payload = {"uid": "A1B2C3D4", "name": "Test"}
    assert client.post("/api/cards", json=payload).status_code == 401
    response = client.post("/api/cards", json=payload, headers={"X-Admin-Token": "test-admin-token"})
    assert response.status_code == 201


def test_rfid_api_key_is_mandatory(client):
    assert client.post("/api/rfid/scan", json={"uid": "A1B2C3D4"}).status_code == 401
    response = client.post("/api/rfid/scan", json={"uid": "A1B2C3D4"}, headers={"X-API-Key": "test-device-key"})
    assert response.status_code == 200
    assert response.json()["allow"] is False


def test_expiry_date_format_is_validated(client):
    payload = {"uid": "A1B2C3D4", "name": "Test", "expires_at": "tomorrow"}
    response = client.post("/api/cards", json=payload, headers={"X-Admin-Token": "test-admin-token"})
    assert response.status_code == 422


def test_expired_card_is_denied(client):
    yesterday = (date.fromisoformat(main.today_business()) - timedelta(days=1)).isoformat()
    payload = {"uid": "A1B2C3D4", "name": "Expired", "expires_at": yesterday}
    created = client.post("/api/cards", json=payload, headers={"X-Admin-Token": "test-admin-token"})
    assert created.status_code == 201
    scan = client.post("/api/rfid/scan", json={"uid": "A1B2C3D4"}, headers={"X-API-Key": "test-device-key"})
    assert scan.status_code == 200
    assert scan.json()["allow"] is False
    assert scan.json()["reason"] == "expired"


def test_daily_quota_is_enforced(client):
    payload = {"uid": "A1B2C3D4", "name": "Quota", "daily_quota": 1}
    created = client.post("/api/cards", json=payload, headers={"X-Admin-Token": "test-admin-token"})
    assert created.status_code == 201
    headers = {"X-API-Key": "test-device-key"}
    first = client.post("/api/rfid/scan", json={"uid": "A1B2C3D4"}, headers=headers)
    second = client.post("/api/rfid/scan", json={"uid": "A1B2C3D4"}, headers=headers)
    assert first.json()["allow"] is True
    assert second.json()["allow"] is False
    assert second.json()["reason"] == "quota_exhausted"


def test_camera_events_get_is_read_only(client):
    with main.db_session() as db:
        db.execute("INSERT INTO security_events(event_at,event_type,track_id,severity,message,details_json,source_event_id) VALUES(?,?,?,?,?,?,?)",
                   (main.now_business(), "test", 1, "warning", "test", "{}", "test-event-1"))
    before = None
    with main.db_session() as db:
        before = db.execute("SELECT COUNT(*) FROM security_events").fetchone()[0]
    response = client.get("/api/camera/events", headers={"X-Admin-Token": "test-admin-token"})
    assert response.status_code == 200
    with main.db_session() as db:
        after = db.execute("SELECT COUNT(*) FROM security_events").fetchone()[0]
    assert after == before


def test_concurrent_scans_cannot_exceed_daily_quota(client):
    from concurrent.futures import ThreadPoolExecutor

    payload = {"uid": "ABCDEF12", "name": "Concurrent", "daily_quota": 1}
    created = client.post("/api/cards", json=payload, headers={"X-Admin-Token": "test-admin-token"})
    assert created.status_code == 201
    headers = {"X-API-Key": "test-device-key"}

    def scan_once(_):
        return client.post("/api/rfid/scan", json={"uid": "ABCDEF12"}, headers=headers).json()["allow"]

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(scan_once, range(2)))
    assert results.count(True) == 1
    assert results.count(False) == 1


def test_rfid_track_association_requires_recent_scan_and_current_track(client, monkeypatch):
    import sys
    from types import SimpleNamespace

    headers = {"X-Admin-Token": "test-admin-token"}
    device_headers = {"X-API-Key": "test-device-key"}
    payload = {"uid": "11223344", "name": "Operator"}
    assert client.post("/api/cards", json=payload, headers=headers).status_code == 201

    # A card with no recent successful scan cannot be attached to a camera track.
    denied = client.post("/api/access/associate", json={"uid": "11223344", "track_id": 7}, headers=headers)
    assert denied.status_code == 409

    scan = client.post("/api/rfid/scan", json={"uid": "11223344"}, headers=device_headers)
    assert scan.json()["allow"] is True

    fake_detector = SimpleNamespace(
        start=lambda: None,
        status=lambda: {"tracked_person_ids": [7]},
        associate_card=lambda track_id, uid, name: {"track_id": track_id, "uid": uid, "name": name, "associated": True},
    )
    monkeypatch.setitem(sys.modules, "ai.person_detector", SimpleNamespace(detector=fake_detector))
    linked = client.post("/api/access/associate", json={"uid": "11223344", "track_id": 7}, headers=headers)
    assert linked.status_code == 200
    assert linked.json()["associated"] is True


def test_retention_prunes_only_records_older_than_cutoff(client):
    old = (date.fromisoformat(main.today_business()) - timedelta(days=10)).isoformat() + "T00:00:00+07:00"
    recent = main.now_business()
    with main.db_session() as db:
        db.execute("INSERT INTO access_logs(uid,card_name,event_at,result) VALUES(?,?,?,?)", ("AABBCCDD", "old", old, "deny"))
        db.execute("INSERT INTO access_logs(uid,card_name,event_at,result) VALUES(?,?,?,?)", ("AABBCCEE", "new", recent, "deny"))
        db.execute("INSERT INTO security_events(event_at,event_type,track_id,severity,message,details_json) VALUES(?,?,?,?,?,?)",
                   (old, "old_event", None, "warning", "old", "{}"))
    result = main.prune_old_logs(retention_days=5)
    assert result["access_logs_deleted"] == 1
    assert result["security_events_deleted"] == 1
    with main.db_session() as db:
        assert db.execute("SELECT COUNT(*) FROM access_logs").fetchone()[0] == 1


def test_sensitive_get_routes_require_admin(client):
    for route in ("/api/cards", "/api/logs", "/api/scans", "/api/alerts", "/api/rfid/last-unknown", "/api/status", "/api/camera/events", "/api/camera/status"):
        assert client.get(route).status_code == 401, route
    headers = {"X-Admin-Token": "test-admin-token"}
    assert client.get("/api/cards", headers=headers).status_code == 200
    assert client.get("/api/alerts", headers=headers).status_code == 200


def test_camera_image_routes_require_session_or_header_auth(client):
    # Auth is checked before attempting to import/start the optional camera stack.
    assert client.get("/api/camera/heatmap").status_code == 401
    assert client.get("/api/camera/snapshot").status_code == 401
    assert client.get("/api/camera/evidence/" + "a" * 32 + ".jpg").status_code == 401


def test_camera_event_low_severity_is_info_not_alarm(client):
    event = {"event_at": main.now_business(), "type": "zone_entry", "severity": "low", "event_id": "routine-entry", "message": "routine"}
    main._sync_usb_camera_events([event])
    with main.db_session() as db:
        row = db.execute("SELECT severity FROM security_events WHERE source_event_id='routine-entry'").fetchone()
    assert row["severity"] == "info"
    assert main.current_alarm_level() == "off"


def test_camera_event_medium_severity_is_warning(client):
    event = {"event_at": main.now_business(), "type": "unauthorized_entry", "severity": "medium", "event_id": "unauthorized-medium", "message": "unauthorized"}
    main._sync_usb_camera_events([event])
    with main.db_session() as db:
        row = db.execute("SELECT severity FROM security_events WHERE source_event_id='unauthorized-medium'").fetchone()
    assert row["severity"] == "warning"
    assert main.current_alarm_level() == "warning"


def test_camera_event_evidence_metadata_updates_existing_row(client):
    event = {"event_at": main.now_business(), "type": "unauthorized_entry", "severity": "high", "event_id": "evidence-race", "message": "entry"}
    main._sync_usb_camera_events([event])
    event["evidence_url"] = "/api/camera/evidence/" + "b" * 32 + ".jpg"
    main._sync_usb_camera_events([event])
    with main.db_session() as db:
        row = db.execute("SELECT details_json FROM security_events WHERE source_event_id='evidence-race'").fetchone()
    assert __import__("json").loads(row["details_json"])["evidence_url"] == event["evidence_url"]


def test_status_open_alerts_excludes_info_and_counts_unacknowledged_alerts(client):
    with main.db_session() as db:
        for severity in ("info", "info", "warning", "severe"):
            db.execute("INSERT INTO security_events(event_at,event_type,track_id,severity,message,details_json) VALUES(?,?,?,?,?,?)",
                       (main.now_business(), "test", None, severity, severity, "{}"))
    response = client.get("/api/status", headers={"X-Admin-Token": "test-admin-token"})
    assert response.status_code == 200
    assert response.json()["open_alerts"] == 2


def test_alerts_default_filter_excludes_info_and_supports_severity_filter(client):
    with main.db_session() as db:
        for severity in ("info", "warning", "severe"):
            db.execute("INSERT INTO security_events(event_at,event_type,track_id,severity,message,details_json) VALUES(?,?,?,?,?,?)",
                       (main.now_business(), "test", None, severity, severity, "{}"))
    headers = {"X-Admin-Token": "test-admin-token"}
    default = client.get("/api/alerts", headers=headers)
    assert default.status_code == 200
    assert {item["severity"] for item in default.json()} == {"warning", "severe"}
    info = client.get("/api/alerts?severity=info", headers=headers)
    assert [item["severity"] for item in info.json()] == ["info"]
    all_events = client.get("/api/alerts?severity=all", headers=headers)
    assert {item["severity"] for item in all_events.json()} == {"info", "warning", "severe"}


def test_openapi_docs_disabled_by_default():
    assert main.app.docs_url is None
    assert main.app.redoc_url is None
    assert main.app.openapi_url is None


def test_admin_api_sets_httponly_cookie_for_media_requests(client):
    response = client.get("/api/status", headers={"X-Admin-Token": "test-admin-token"})
    assert response.status_code == 200
    cookie = response.headers.get("set-cookie", "")
    assert "khoai_admin_session=" in cookie
    assert "httponly" in cookie.lower()
    # Cookie is accepted for media auth; downstream may return 503 when no USB camera is attached,
    # but it must not reject the request as unauthenticated.
    media = client.get("/api/camera/snapshot")
    assert media.status_code != 401


def test_stats_alerts_today_excludes_info(client):
    with main.db_session() as db:
        for severity in ("info", "warning", "severe"):
            db.execute(
                "INSERT INTO security_events(event_at,event_type,track_id,severity,message,details_json) VALUES(?,?,?,?,?,?)",
                (main.now_business(), "test_stats", None, severity, severity, "{}"),
            )
    response = client.get("/api/stats", headers={"X-Admin-Token": "test-admin-token"})
    assert response.status_code == 200
    assert response.json()["alerts_today"] == 2


def test_media_auth_ignores_bad_cookie_when_header_is_valid(client):
    response = client.get(
        "/api/camera/snapshot",
        cookies={"khoai_admin_session": "stale-cookie"},
        headers={"X-Admin-Token": "test-admin-token"},
    )
    assert response.status_code != 401


def test_media_auth_rejects_query_string_token(client):
    response = client.get("/api/camera/snapshot?token=test-admin-token")
    assert response.status_code == 401


def test_credential_compare_handles_non_ascii_without_500():
    assert main._credential_matches("mật-khẩu", "mật-khẩu") is True
    assert main._credential_matches("mật-khẩU", "mật-khẩu") is False
