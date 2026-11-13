from datetime import date, timedelta

import asyncio
import pytest
from fastapi.testclient import TestClient

from backend.app import main


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "test.sqlite3")
    monkeypatch.setattr(main, "CAMERA_AUTOSTART", False)
    # API tests drive detector events explicitly. Disable the periodic event-sync
    # writer so it cannot race tests that assert read-only incident behavior.
    async def idle_event_worker():
        await asyncio.sleep(3600)
    monkeypatch.setattr(main, "_camera_event_sync_worker", idle_event_worker)
    monkeypatch.setenv("KHOAI_ADMIN_TOKEN", "test-admin-token-0123456789-abcdef")
    monkeypatch.setenv("KHOAI_API_KEY", "test-device-key-for-khoai-automated-tests-2026")
    with main._auth_lock:
        main._auth_failures.clear()
    main.init_db()
    with TestClient(main.app) as test_client:
        yield test_client


def test_write_routes_require_admin_token(client):
    payload = {"uid": "A1B2C3D4", "name": "Test"}
    assert client.post("/api/cards", json=payload).status_code == 401
    response = client.post("/api/cards", json=payload, headers={"X-Admin-Token": "test-admin-token-0123456789-abcdef"})
    assert response.status_code == 201


def test_rfid_api_key_is_mandatory(client):
    assert client.post("/api/rfid/scan", json={"uid": "A1B2C3D4"}).status_code == 401
    response = client.post("/api/rfid/scan", json={"uid": "A1B2C3D4"}, headers={"X-API-Key": "test-device-key-for-khoai-automated-tests-2026"})
    assert response.status_code == 200
    assert response.json()["allow"] is False


def test_expiry_date_format_is_validated(client):
    payload = {"uid": "A1B2C3D4", "name": "Test", "expires_at": "tomorrow"}
    response = client.post("/api/cards", json=payload, headers={"X-Admin-Token": "test-admin-token-0123456789-abcdef"})
    assert response.status_code == 422


def test_expired_card_is_denied(client):
    yesterday = (date.fromisoformat(main.today_business()) - timedelta(days=1)).isoformat()
    payload = {"uid": "A1B2C3D4", "name": "Expired", "expires_at": yesterday}
    created = client.post("/api/cards", json=payload, headers={"X-Admin-Token": "test-admin-token-0123456789-abcdef"})
    assert created.status_code == 201
    scan = client.post("/api/rfid/scan", json={"uid": "A1B2C3D4"}, headers={"X-API-Key": "test-device-key-for-khoai-automated-tests-2026"})
    assert scan.status_code == 200
    assert scan.json()["allow"] is False
    assert scan.json()["reason"] == "expired"


def test_daily_quota_is_enforced(client, monkeypatch):
    monkeypatch.setattr(main, "RFID_SCAN_DEBOUNCE_SECONDS", 0)
    payload = {"uid": "A1B2C3D4", "name": "Quota", "daily_quota": 1}
    created = client.post("/api/cards", json=payload, headers={"X-Admin-Token": "test-admin-token-0123456789-abcdef"})
    assert created.status_code == 201
    headers = {"X-API-Key": "test-device-key-for-khoai-automated-tests-2026"}
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
    response = client.get("/api/camera/events", headers={"X-Admin-Token": "test-admin-token-0123456789-abcdef"})
    assert response.status_code == 200
    with main.db_session() as db:
        after = db.execute("SELECT COUNT(*) FROM security_events").fetchone()[0]
    assert after == before


def test_concurrent_scans_cannot_exceed_daily_quota(client):
    from concurrent.futures import ThreadPoolExecutor

    payload = {"uid": "ABCDEF12", "name": "Concurrent", "daily_quota": 1}
    created = client.post("/api/cards", json=payload, headers={"X-Admin-Token": "test-admin-token-0123456789-abcdef"})
    assert created.status_code == 201
    headers = {"X-API-Key": "test-device-key-for-khoai-automated-tests-2026"}

    def scan_once(_):
        return client.post("/api/rfid/scan", json={"uid": "ABCDEF12"}, headers=headers).json()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(scan_once, range(2)))
    assert sum(bool(result["allow"]) for result in results) == 1
    assert sum(bool(result["deduplicated"]) for result in results) == 1
    with main.db_session() as db:
        used = db.execute("SELECT used_today FROM cards WHERE uid='ABCDEF12'").fetchone()[0]
        assert used == 1


def test_rapid_duplicate_rfid_scan_does_not_consume_quota_twice(client):
    payload = {"uid": "0A0B0C0D", "name": "Debounce", "daily_quota": 2, "zones": []}
    admin_headers = {"X-Admin-Token": "test-admin-token-0123456789-abcdef"}
    assert client.post("/api/cards", json=payload, headers=admin_headers).status_code == 201
    device_headers = {"X-API-Key": "test-device-key-for-khoai-automated-tests-2026"}
    first = client.post("/api/rfid/scan", json={"uid": "0A0B0C0D", "device_id": "gate01"}, headers=device_headers).json()
    duplicate = client.post("/api/rfid/scan", json={"uid": "0A0B0C0D", "device_id": "gate01"}, headers=device_headers).json()
    second_reader = client.post("/api/rfid/scan", json={"uid": "0A0B0C0D", "device_id": "gate02"}, headers=device_headers).json()
    assert first["allow"] is True and first["deduplicated"] is False
    assert duplicate["allow"] is False and duplicate["reason"] == "duplicate_scan"
    assert duplicate["deduplicated"] is True
    assert second_reader["allow"] is True and second_reader["deduplicated"] is False
    with main.db_session() as db:
        row = db.execute("SELECT used_today FROM cards WHERE uid='0A0B0C0D'").fetchone()
        assert row[0] == 2


def test_rfid_track_association_requires_recent_scan_and_current_track(client, monkeypatch):
    import sys
    from types import SimpleNamespace

    headers = {"X-Admin-Token": "test-admin-token-0123456789-abcdef"}
    device_headers = {"X-API-Key": "test-device-key-for-khoai-automated-tests-2026"}
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
        associate_card=lambda track_id, uid, name, allowed_zones=(): {"track_id": track_id, "uid": uid, "name": name, "allowed_zones": list(allowed_zones), "associated": True},
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
    headers = {"X-Admin-Token": "test-admin-token-0123456789-abcdef"}
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


def test_camera_event_medium_severity_is_history_not_live_alarm(client):
    event = {"event_at": main.now_business(), "type": "unauthorized_entry", "severity": "medium", "event_id": "unauthorized-medium", "message": "unauthorized"}
    main._sync_usb_camera_events([event])
    with main.db_session() as db:
        row = db.execute("SELECT severity FROM security_events WHERE source_event_id='unauthorized-medium'").fetchone()
    assert row["severity"] == "warning"
    # Persisted events are historical records; live alarm comes only from DecisionEngine.
    assert main.current_alarm_level() == "off"


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
    response = client.get("/api/status", headers={"X-Admin-Token": "test-admin-token-0123456789-abcdef"})
    assert response.status_code == 200
    assert response.json()["open_alerts"] == 2


def test_alerts_default_filter_excludes_info_and_supports_severity_filter(client):
    with main.db_session() as db:
        for severity in ("info", "warning", "severe"):
            db.execute("INSERT INTO security_events(event_at,event_type,track_id,severity,message,details_json) VALUES(?,?,?,?,?,?)",
                       (main.now_business(), "test", None, severity, severity, "{}"))
    headers = {"X-Admin-Token": "test-admin-token-0123456789-abcdef"}
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
    response = client.get("/api/status", headers={"X-Admin-Token": "test-admin-token-0123456789-abcdef"})
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
    response = client.get("/api/stats", headers={"X-Admin-Token": "test-admin-token-0123456789-abcdef"})
    assert response.status_code == 200
    assert response.json()["alerts_today"] == 2


def test_media_auth_ignores_bad_cookie_when_header_is_valid(client):
    response = client.get(
        "/api/camera/snapshot",
        cookies={"khoai_admin_session": "stale-cookie"},
        headers={"X-Admin-Token": "test-admin-token-0123456789-abcdef"},
    )
    assert response.status_code != 401


def test_media_auth_rejects_query_string_token(client):
    response = client.get("/api/camera/snapshot?token=test-admin-token-0123456789-abcdef")
    assert response.status_code == 401


def test_credential_compare_handles_non_ascii_without_500():
    assert main._credential_matches("mật-khẩu", "mật-khẩu") is True
    assert main._credential_matches("mật-khẩU", "mật-khẩu") is False


def test_live_alarm_level_comes_from_decision_engine_not_event_database(monkeypatch):
    import sys
    from types import SimpleNamespace

    fake_detector = SimpleNamespace(status=lambda: {"alarm_state": "ALARM"})
    monkeypatch.setitem(sys.modules, "ai.person_detector", SimpleNamespace(detector=fake_detector))
    assert main.current_alarm_level() == "severe"
    fake_detector.status = lambda: {"alarm_state": "WARNING"}
    assert main.current_alarm_level() == "warning"
    fake_detector.status = lambda: {"alarm_state": "SAFE"}
    assert main.current_alarm_level() == "off"


def test_card_lock_revokes_all_detector_authorizations(client, monkeypatch):
    import sys
    from types import SimpleNamespace
    revoked = []
    fake_detector = SimpleNamespace(revoke_uid=lambda uid: revoked.append(uid))
    monkeypatch.setitem(sys.modules, "ai.person_detector", SimpleNamespace(detector=fake_detector))
    headers = {"X-Admin-Token": "test-admin-token-0123456789-abcdef"}
    assert client.post("/api/cards", json={"uid": "ABCDEF99", "name": "Operator"}, headers=headers).status_code == 201
    response = client.patch("/api/cards/ABCDEF99", json={"active": False}, headers=headers)
    assert response.status_code == 200 and response.json()["active"] is False
    assert revoked == ["ABCDEF99"]
    with main.db_session() as db:
        assert db.execute("SELECT active FROM cards WHERE uid='ABCDEF99'").fetchone()[0] == 0


def test_incident_latch_ack_and_resolution_lifecycle(client, monkeypatch):
    import sys
    from types import SimpleNamespace
    state = {"alarm_state": "ALARM"}
    fake_detector = SimpleNamespace(status=lambda: dict(state))
    monkeypatch.setitem(sys.modules, "ai.person_detector", SimpleNamespace(detector=fake_detector))
    now = main.now_business()
    main._sync_usb_camera_events([
        {"event_id": "incident-alarm-state", "event_at": now, "type": "alarm_state_changed",
         "state": "ALARM", "severity": "critical", "track_id": -1},
        {"event_id": "incident-entry", "event_at": now, "type": "unauthorized_entry",
         "severity": "critical", "track_id": 7},
    ])
    headers = {"X-Admin-Token": "test-admin-token-0123456789-abcdef"}
    incidents = client.get("/api/incidents", headers=headers).json()
    assert len(incidents) == 1 and incidents[0]["status"] == "OPEN"
    incident_id = incidents[0]["incident_id"]
    ack = client.post(f"/api/incidents/{incident_id}/ack", json={}, headers=headers)
    assert ack.status_code == 200
    assert ack.json()["latched"] is True and ack.json()["acknowledged"] is True
    assert ack.json()["siren"] is True
    # Acknowledgement while the threat is active must not close the incident.
    assert client.get("/api/incidents", headers=headers).json()[0]["status"] == "OPEN"
    state["alarm_state"] = "SAFE"
    main._sync_usb_camera_events([{"event_id": "incident-safe", "event_at": main.now_business(),
                                   "type": "alarm_state_changed", "state": "SAFE", "severity": "info"}])
    assert client.get("/api/incidents", headers=headers).json()[0]["status"] == "CLOSED"


def test_admin_session_has_server_side_expiry(client):
    headers = {"X-Admin-Token": "test-admin-token-0123456789-abcdef"}
    response = client.get("/api/status", headers=headers)
    assert response.status_code == 200
    cookie = client.cookies.get("khoai_admin_session")
    assert cookie and cookie != "test-admin-token-0123456789-abcdef"
    with main.db_session() as db:
        db.execute("UPDATE admin_sessions SET expires_at=0 WHERE session_id=?", (main._session_digest(cookie),))
    assert client.get("/api/status").status_code == 401


def test_wrong_admin_tokens_are_rate_limited(client):
    for _ in range(main.AUTH_RATE_LIMIT):
        response = client.get("/api/status", headers={"X-Admin-Token": "incorrect-token"})
        assert response.status_code == 401
    blocked = client.get("/api/status", headers={"X-Admin-Token": "incorrect-token"})
    assert blocked.status_code == 429


def test_inside_camera_proxy_requires_admin_and_server_configuration(client, monkeypatch):
    monkeypatch.delenv("KHOAI_ESP32_CAM_STREAM_URL", raising=False)
    assert client.get("/api/camera/inside/stream").status_code == 401
    headers = {"X-Admin-Token": "test-admin-token-0123456789-abcdef"}
    response = client.get("/api/camera/inside/stream", headers=headers)
    assert response.status_code == 503


def test_rfid_scan_issues_short_lived_ticket(client, monkeypatch):
    import sys
    from types import SimpleNamespace
    tickets = []
    fake_detector = SimpleNamespace(create_rfid_ticket=lambda uid, name, zones, ttl_seconds: tickets.append((uid, ttl_seconds)) or {"pending_binding": True})
    monkeypatch.setitem(sys.modules, "ai.person_detector", SimpleNamespace(detector=fake_detector, RFID_TICKET_SECONDS=20.0))
    headers = {"X-Admin-Token": "test-admin-token-0123456789-abcdef"}
    assert client.post("/api/cards", json={"uid": "BEEFCafe", "name": "Worker", "zones": ["external_usb_zone"]}, headers=headers).status_code == 201
    scan = client.post("/api/rfid/scan", json={"uid": "BEEFCafe"}, headers={"X-API-Key": "test-device-key-for-khoai-automated-tests-2026"})
    assert scan.status_code == 200 and scan.json()["allow"] is True
    assert tickets == [("BEEFCAFE", 20.0)]


def test_device_registry_accepts_only_matching_device_key(client, monkeypatch):
    import json
    key = "A9" * 32
    monkeypatch.setenv("KHOAI_DEVICE_API_KEYS_JSON", json.dumps({"gate01": key}))
    response = client.post("/api/rfid/scan", json={"uid": "A1B2C3D4", "device_id": "gate01"},
                           headers={"X-API-Key": key, "X-Device-ID": "gate01"})
    assert response.status_code == 200
    wrong_device = client.post("/api/rfid/scan", json={"uid": "A1B2C3D4", "device_id": "gate01"},
                               headers={"X-API-Key": key, "X-Device-ID": "gate02"})
    assert wrong_device.status_code == 401
    mismatched_body = client.post("/api/rfid/scan", json={"uid": "A1B2C3D4", "device_id": "gate02"},
                                  headers={"X-API-Key": key, "X-Device-ID": "gate01"})
    assert mismatched_body.status_code == 400


def test_security_headers_are_set_for_http_responses(client, monkeypatch):
    monkeypatch.delenv("KHOAI_CSP_MODE", raising=False)
    response = client.get("/api/health")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert "script-src 'self'" in response.headers["content-security-policy-report-only"]


def test_intrusion_incident_remains_latched_when_anti_theft_is_disabled(client, monkeypatch):
    import sys
    from types import SimpleNamespace
    state = {"alarm_state": "ALARM", "anti_theft_enabled": True}
    monkeypatch.setitem(sys.modules, "ai.person_detector", SimpleNamespace(detector=SimpleNamespace(status=lambda: dict(state))))
    main._sync_usb_camera_events([{"event_id": "disable-latch-alarm", "event_at": main.now_business(),
        "type": "alarm_state_changed", "state": "ALARM", "severity": "critical", "track_id": -1}])
    headers = {"X-Admin-Token": "test-admin-token-0123456789-abcdef"}
    incident = client.get("/api/incidents", headers=headers).json()[0]
    ack = client.post(f"/api/incidents/{incident['incident_id']}/ack", json={}, headers=headers)
    assert ack.status_code == 200
    state.update({"alarm_state": "SAFE", "anti_theft_enabled": False})
    # Disarming is not proof that the zone is clear; the acknowledged latch remains open.
    assert client.get("/api/incidents", headers=headers).json()[0]["status"] == "OPEN"


def test_health_incidents_auto_close_on_recovery(client):
    headers = {"X-Admin-Token": "test-admin-token-0123456789-abcdef"}
    main._sync_usb_camera_events([{"event_id": "camera-down-health", "event_at": main.now_business(),
        "type": "camera_offline", "severity": "critical", "track_id": -1}])
    incident = client.get("/api/incidents", headers=headers).json()[0]
    assert incident["type"] == "camera_outage" and incident["status"] == "OPEN"
    main._sync_usb_camera_events([{"event_id": "camera-up-health", "event_at": main.now_business(),
        "type": "camera_recovered", "severity": "info", "track_id": -1}])
    closed = client.get("/api/incidents", headers=headers).json()[0]
    assert closed["status"] == "CLOSED"


def test_new_alarm_after_incident_ack_resets_ack_and_siren(client, monkeypatch):
    import sys
    from types import SimpleNamespace
    monkeypatch.setitem(sys.modules, "ai.person_detector", SimpleNamespace(detector=SimpleNamespace(status=lambda: {"alarm_state": "ALARM"})))
    headers = {"X-Admin-Token": "test-admin-token-0123456789-abcdef"}
    main._sync_usb_camera_events([{"event_id": "ack-reset-first", "event_at": main.now_business(),
        "type": "unauthorized_entry", "severity": "critical", "track_id": 10}])
    incident = client.get("/api/incidents", headers=headers).json()[0]
    client.post(f"/api/incidents/{incident['incident_id']}/ack", json={}, headers=headers)
    main._sync_usb_camera_events([{"event_id": "ack-reset-second", "event_at": main.now_business(),
        "type": "unauthorized_entry", "severity": "critical", "track_id": 11}])
    updated = client.get("/api/incidents", headers=headers).json()[0]
    assert updated["incident_id"] == incident["incident_id"]
    assert updated["acknowledged"] is False and updated["siren"] is True


def test_repeated_event_sync_does_not_reset_incident_ack(client, monkeypatch):
    import sys
    from types import SimpleNamespace
    monkeypatch.setitem(sys.modules, "ai.person_detector", SimpleNamespace(detector=SimpleNamespace(status=lambda: {"alarm_state": "ALARM"})))
    headers = {"X-Admin-Token": "test-admin-token-0123456789-abcdef"}
    event = {"event_id": "same-event-replayed", "event_at": main.now_business(),
             "type": "unauthorized_entry", "severity": "critical", "track_id": 88}
    main._sync_usb_camera_events([event])
    incident = client.get("/api/incidents", headers=headers).json()[0]
    client.post(f"/api/incidents/{incident['incident_id']}/ack", json={}, headers=headers)
    # The background worker replays the detector's recent event deque; replay is idempotent.
    main._sync_usb_camera_events([event])
    updated = client.get("/api/incidents", headers=headers).json()[0]
    assert updated["acknowledged"] is True
    assert updated["siren"] is True
    assert updated["event_count"] == 1


def test_incident_event_receives_late_evidence_metadata(client):
    event = {"event_id": "incident-evidence-late", "event_at": main.now_business(),
             "type": "unauthorized_entry", "severity": "critical", "track_id": 91}
    main._sync_usb_camera_events([event])
    event["evidence_url"] = "/api/camera/evidence/" + "c" * 32 + ".jpg"
    event["evidence_reused"] = True
    event["image_age_ms"] = 500.0
    main._sync_usb_camera_events([event])
    with main.db_session() as db:
        row = db.execute("SELECT details_json FROM incident_events WHERE source_event_id='incident-evidence-late'").fetchone()
    details = __import__("json").loads(row["details_json"])
    assert details["evidence_url"] == event["evidence_url"]
    assert details["evidence_reused"] is True
    assert details["incident_id"]


def test_admin_secret_rejects_sample_and_short_values():
    import pytest
    with pytest.raises(main.HTTPException):
        main._validate_admin_secret("short-secret")
    with pytest.raises(main.HTTPException):
        main._validate_admin_secret("REPLACE_WITH_A_UNIQUE_RANDOM_SECRET_MINIMUM_24_CHARS")
    main._validate_admin_secret("a-unique-production-admin-token-0123456789")


def test_health_endpoint_uses_single_version_source(client, monkeypatch):
    import sys
    from types import SimpleNamespace
    fake_detector = SimpleNamespace(status=lambda: {"camera_ok": False, "ai_ok": True, "tracking_enabled": True})
    monkeypatch.setitem(sys.modules, "ai.person_detector", SimpleNamespace(detector=fake_detector))
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["version"] == (main.ROOT / "VERSION.txt").read_text().strip()
    assert response.json()["camera_ok"] is False
    assert response.json()["status"] == "degraded"


def test_health_alarm_state_field_creates_health_incident_and_siren(client):
    event = {"event_id": "health-alarm-state", "event_at": main.now_business(),
             "type": "alarm_state_changed", "alarm_state": "ALARM", "reason": "health_fault",
             "health_reason": "camera_offline", "severity": "critical", "track_id": -1}
    main._sync_usb_camera_events([event])
    headers = {"X-Admin-Token": "test-admin-token-0123456789-abcdef"}
    incident = client.get("/api/incidents", headers=headers).json()[0]
    assert incident["type"] == "camera_outage"
    assert incident["siren"] is True


def test_incident_status_read_does_not_close_incident(client, monkeypatch):
    monkeypatch.setattr(main, "_current_detector_state", lambda: "SAFE")
    incident_id = "a" * 32
    with main.db_session() as db:
        db.execute("""INSERT INTO incidents(incident_id,incident_type,started_at,updated_at,status,acknowledged,siren_until)
            VALUES(?,?,?,?,'OPEN',1,0)""", (incident_id, "intrusion", main.now_business(), main.now_business()))
    status = main._incident_status()
    assert status["latched"] is True
    with main.db_session() as db:
        row = db.execute("SELECT status FROM incidents WHERE incident_id=?", (incident_id,)).fetchone()
    assert row["status"] == "OPEN"


def test_rfid_and_heartbeat_return_siren_separately(client):
    headers = {"X-API-Key": "test-device-key-for-khoai-automated-tests-2026"}
    scan = client.post("/api/rfid/scan", json={"uid": "A1B2C3D4"}, headers=headers)
    assert scan.status_code == 200
    assert "alarm" in scan.json() and "siren" in scan.json()
    heartbeat = client.post("/api/device/heartbeat", json={"device_id": "gate01"}, headers=headers)
    assert heartbeat.status_code == 200
    assert "alarm" in heartbeat.json() and "siren" in heartbeat.json()


def test_evidence_retention_removes_old_unreferenced_but_keeps_open_incident_files(client, monkeypatch, tmp_path):
    import os
    evidence_dir = tmp_path / "evidence"
    evidence_dir.mkdir()
    old_unreferenced = evidence_dir / ("1" * 32 + ".jpg")
    old_referenced = evidence_dir / ("2" * 32 + ".jpg")
    old_unreferenced.write_bytes(b"old")
    old_referenced.write_bytes(b"critical")
    old_ts = main.time.time() - 3 * 86400
    os.utime(old_unreferenced, (old_ts, old_ts))
    os.utime(old_referenced, (old_ts, old_ts))
    monkeypatch.setenv("KHOAI_EVIDENCE_MAX_AGE_DAYS", "1")
    incident_id = "c" * 32
    with main.db_session() as db:
        db.execute("""INSERT INTO incidents(incident_id,incident_type,started_at,updated_at,status,acknowledged,siren_until)
            VALUES(?,?,?,?,'OPEN',0,0)""", (incident_id, "intrusion", main.now_business(), main.now_business()))
        db.execute("""INSERT INTO incident_events(incident_id,source_event_id,event_type,event_at,details_json)
            VALUES(?,?,?,?,?)""", (incident_id, "protected-evidence", "unauthorized_entry", main.now_business(),
            __import__("json").dumps({"evidence_url": "/api/camera/evidence/" + old_referenced.name})))
    assert main.prune_evidence_files(evidence_dir) == 1
    assert not old_unreferenced.exists()
    assert old_referenced.exists()


def test_incidents_are_grouped_by_engine_session_id(client):
    now = main.now_business()
    main._sync_usb_camera_events([
        {"event_id": "session-a-1", "event_at": now, "type": "unauthorized_entry",
         "severity": "critical", "track_id": 11, "session_id": "session-a"},
        {"event_id": "session-a-2", "event_at": now, "type": "unauthorized_entry",
         "severity": "critical", "track_id": 12, "session_id": "session-a"},
        {"event_id": "session-b-1", "event_at": now, "type": "unauthorized_entry",
         "severity": "critical", "track_id": 13, "session_id": "session-b"},
    ])
    with main.db_session() as db:
        rows = db.execute("SELECT session_id, COUNT(*) AS n FROM incidents WHERE session_id IN ('session-a','session-b') GROUP BY session_id").fetchall()
    counts = {row["session_id"]: row["n"] for row in rows}
    assert counts == {"session-a": 1, "session-b": 1}


def test_closed_attempt_incident_is_still_grouped_by_session_id(client):
    now = main.now_business()
    main._sync_usb_camera_events([
        {"event_id": "attempt-session-1", "event_at": now, "type": "intrusion_attempt_aborted",
         "severity": "warning", "track_id": 21, "session_id": "attempt-session"},
        {"event_id": "attempt-session-2", "event_at": now, "type": "intrusion_attempt_aborted",
         "severity": "warning", "track_id": 21, "session_id": "attempt-session"},
    ])
    with main.db_session() as db:
        rows = db.execute("SELECT incident_id,status,event_count FROM incidents WHERE session_id='attempt-session'").fetchall()
    assert len(rows) == 1
    assert rows[0]["status"] == "CLOSED"
    assert rows[0]["event_count"] == 1  # duplicate source event is suppressed by cooldown


def test_new_card_defaults_to_external_usb_camera_permission(client):
    headers = {"X-Admin-Token": "test-admin-token-0123456789-abcdef"}
    created = client.post("/api/cards", json={"uid": "C0FFEE01", "name": "Default camera"}, headers=headers)
    assert created.status_code == 201
    listed = client.get("/api/cards", headers=headers)
    card = next(item for item in listed.json() if item["uid"] == "C0FFEE01")
    assert "external_usb_zone" in card["zones"]


def test_rfid_scan_explains_missing_external_usb_camera_permission(client, monkeypatch):
    import sys
    from types import SimpleNamespace
    fake_detector = SimpleNamespace(create_rfid_ticket=lambda *args, **kwargs: pytest.fail("No camera ticket expected"))
    monkeypatch.setitem(sys.modules, "ai.person_detector", SimpleNamespace(
        detector=fake_detector, RFID_TICKET_SECONDS=20.0, CAMERA_ZONE_ID="external_usb_zone"))
    headers = {"X-Admin-Token": "test-admin-token-0123456789-abcdef"}
    created = client.post("/api/cards", json={"uid": "C0FFEE02", "name": "No camera", "zones": ["entry"]}, headers=headers)
    assert created.status_code == 201
    scan = client.post("/api/rfid/scan", json={"uid": "C0FFEE02"}, headers={"X-API-Key": "test-device-key-for-khoai-automated-tests-2026"})
    assert scan.status_code == 200
    data = scan.json()
    assert data["allow"] is True  # door/business permission is independent
    assert data["camera_permission"] is False
    assert data["camera_message"] == "Thẻ chưa có quyền Camera USB ngoài."
    assert data["ticket"] is None


def test_rfid_entry_roi_can_be_saved_through_admin_api(client, monkeypatch):
    import sys
    from types import SimpleNamespace
    detector = SimpleNamespace(rfid_entry_roi=())
    def set_roi(points):
        detector.rfid_entry_roi = tuple((float(x), float(y)) for x, y in points)
        return detector.rfid_entry_roi
    detector.set_rfid_entry_roi = set_roi
    monkeypatch.setitem(sys.modules, "ai.person_detector", SimpleNamespace(detector=detector))
    headers = {"X-Admin-Token": "test-admin-token-0123456789-abcdef"}
    points = [[0.1, 0.2], [0.9, 0.2], [0.9, 0.8], [0.1, 0.8]]
    saved = client.put("/api/rfid/entry-roi", json={"points": points}, headers=headers)
    assert saved.status_code == 200
    assert saved.json()["points"] == points
    loaded = client.get("/api/rfid/entry-roi", headers=headers)
    assert loaded.status_code == 200 and loaded.json()["points"] == points


def test_pending_rfid_api_lists_tickets_and_live_tracks(client, monkeypatch):
    import sys
    from types import SimpleNamespace
    fake_detector = SimpleNamespace(
        start=lambda: None,
        status=lambda: {"tracked_person_ids": [7], "decision_tracks": {"7": {"state": "WARNING"}}},
        pending_rfid_tickets=lambda: [{"uid": "AABBCCDD", "name": "Worker", "expires_in": 10.0}],
    )
    monkeypatch.setitem(sys.modules, "ai.person_detector", SimpleNamespace(detector=fake_detector))
    headers = {"X-Admin-Token": "test-admin-token-0123456789-abcdef"}
    result = client.get("/api/rfid/pending", headers=headers)
    assert result.status_code == 200
    assert result.json()["tickets"][0]["uid"] == "AABBCCDD"
    assert result.json()["tracks"][0]["track_id"] == 7


def test_track_thumbnail_api_serves_only_admin_authorized_image(client, monkeypatch):
    import sys
    from types import SimpleNamespace
    fake_detector = SimpleNamespace(track_thumbnail_jpeg=lambda track_id: b"jpeg" if track_id == 7 else None)
    monkeypatch.setitem(sys.modules, "ai.person_detector", SimpleNamespace(detector=fake_detector))
    headers = {"X-Admin-Token": "test-admin-token-0123456789-abcdef"}
    result = client.get("/api/camera/tracks/7/thumbnail", headers=headers)
    assert result.status_code == 200 and result.content == b"jpeg"
    assert client.get("/api/camera/tracks/8/thumbnail", headers=headers).status_code == 404
