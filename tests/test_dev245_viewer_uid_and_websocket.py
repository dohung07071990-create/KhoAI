import asyncio

import pytest
from fastapi import HTTPException


def test_viewer_payload_masks_known_uid_in_free_text_across_nested_records():
    from backend.app.main import _mask_uid_payload

    source = {
        "alerts": [{
            "message": "Quẹt thẻ bị từ chối: A1B2C3D4",
            "details": {"uid": "A1B2C3D4", "reason": "unknown_card"},
        }],
        "timeline": [{
            "explanation": "authorization_revoked for A1B2C3D4",
            "details": {"card_uid": "A1B2C3D4"},
        }],
        "other": "Track 1042, 3600 giây, ngày 2026-11-11, face added",
    }
    result = _mask_uid_payload(source)
    assert result["alerts"][0]["details"]["uid"] == "****C3D4"
    assert result["alerts"][0]["message"] == "Quẹt thẻ bị từ chối: ****C3D4"
    assert result["timeline"][0]["details"]["card_uid"] == "****C3D4"
    assert result["timeline"][0]["explanation"] == "authorization_revoked for ****C3D4"
    assert result["other"] == source["other"]


def test_viewer_uid_redaction_does_not_replace_uid_substrings_inside_words():
    from backend.app.main import _mask_uid_payload

    source = {"uid": "FACE", "message": "FACE was denied; interface is available"}
    result = _mask_uid_payload(source)
    assert result["uid"] == "****"
    assert result["message"] == "**** was denied; interface is available"


def test_telegram_lease_heartbeat_retries_immediately_after_transient_error():
    from backend.app.telegram.bot import _lease_heartbeat_loop

    async def run():
        calls = []
        sleeps = []

        def lease(action, owner, ttl):
            calls.append((action, owner, ttl))
            if len(calls) == 1:
                raise sqlite3.OperationalError("database is locked")
            return True

        async def fake_sleep(delay):
            sleeps.append(delay)
            if len(calls) >= 2 and delay == 20.0:
                raise asyncio.CancelledError

        try:
            await _lease_heartbeat_loop(lease, "owner", ttl=60, interval=20.0, sleep=fake_sleep)
        except asyncio.CancelledError:
            pass
        assert len(calls) == 2
        assert sleeps[:2] == [20.0, 1.0]

    import sqlite3
    asyncio.run(run())


def test_websocket_closes_fail_closed_when_session_validation_raises_503(monkeypatch):
    import backend.app.main as backend

    class Manager:
        def connect(self, *_args):
            return "session"
        def disconnect(self, *_args):
            pass
        def snapshot(self):
            return {}

    class WebSocket:
        headers = {"host": "localhost"}
        cookies = {"khoai_admin_session": "cookie-value"}
        def __init__(self):
            self.closed = []
        async def close(self, code):
            self.closed.append(code)
        async def accept(self):
            raise AssertionError("must not accept when initial validation fails")

    async def invalid(_digest):
        raise HTTPException(status_code=503, detail="database unavailable")

    async def run():
        monkeypatch.setattr(backend, "_session_digest_valid_cached", invalid)
        monkeypatch.setattr(backend.app.state, "stream_manager", Manager(), raising=False)
        ws = WebSocket()
        await backend.camera_streams_websocket(ws)
        assert ws.closed == [1013]

    asyncio.run(run())


def test_websocket_revalidates_session_asynchronously_and_closes_on_503(monkeypatch):
    import backend.app.main as backend

    class Manager:
        def __init__(self):
            self.disconnected = False
        def connect(self, *_args):
            return "session"
        def disconnect(self, *_args):
            self.disconnected = True
        def snapshot(self):
            return {}

    class WebSocket:
        headers = {"host": "localhost"}
        cookies = {"khoai_admin_session": "cookie-value"}
        def __init__(self):
            self.closed = []
            self.accepted = False
        async def close(self, code):
            self.closed.append(code)
        async def accept(self):
            self.accepted = True
        async def send_json(self, _payload):
            pass

    calls = 0
    async def validation(_digest):
        nonlocal calls
        calls += 1
        if calls == 1:
            return True
        raise HTTPException(status_code=503, detail="database unavailable")

    async def run():
        manager = Manager()
        monkeypatch.setattr(backend, "_session_digest_valid_cached", validation)
        monkeypatch.setattr(backend.app.state, "stream_manager", manager, raising=False)
        ws = WebSocket()
        await backend.camera_streams_websocket(ws)
        assert ws.accepted
        assert ws.closed == [1013]
        assert manager.disconnected

    asyncio.run(run())


def test_viewer_masks_registered_uid_even_when_message_has_no_structured_uid(monkeypatch):
    import backend.app.main as backend

    monkeypatch.setattr(backend, "_known_card_uids_for_redaction", lambda: {"A1B2C3D4"})
    source = {
        "message": "Thẻ bị từ chối: A1B2C3D4; Track 1042; 3600 giây; dead beef 2026",
        "explanation": "authorization_revoked for A1B2C3D4",
    }
    result = backend._mask_uid_payload(source)
    assert result["message"] == "Thẻ bị từ chối: ****C3D4; Track 1042; 3600 giây; dead beef 2026"
    assert result["explanation"] == "authorization_revoked for ****C3D4"


def test_session_sqlite_error_is_not_cached_as_invalid(monkeypatch):
    import backend.app.main as backend

    class BrokenDB:
        def __enter__(self):
            raise sqlite3.OperationalError("database is locked")
        def __exit__(self, *_args):
            return False

    monkeypatch.setattr(backend, "db_session", lambda: BrokenDB())
    backend._session_validation_cache.clear()

    async def run():
        with pytest.raises(backend.SessionValidationUnavailable):
            await backend._session_digest_valid_cached("transient-db-error")
        assert "transient-db-error" not in backend._session_validation_cache

    import sqlite3
    asyncio.run(run())


def test_lease_heartbeat_stops_before_unconfirmed_lease_expiry():
    from backend.app.telegram.bot import _lease_heartbeat_loop

    async def run():
        now = [0.0]
        calls = []
        sleeps = []

        def monotonic():
            return now[0]

        async def fake_sleep(delay):
            sleeps.append(delay)
            now[0] += delay

        def lease(action, owner, ttl):
            calls.append((action, owner, ttl))
            raise sqlite3.OperationalError("database is locked")

        with pytest.raises(RuntimeError, match="before expiry|near expiry"):
            await _lease_heartbeat_loop(lease, "owner", ttl=30, interval=10,
                                        sleep=fake_sleep, monotonic=monotonic,
                                        safety_margin=5)
        assert calls
        assert now[0] < 30
        assert now[0] >= 25

    import sqlite3
    asyncio.run(run())
