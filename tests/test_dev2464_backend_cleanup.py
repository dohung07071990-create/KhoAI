from __future__ import annotations

import asyncio
import sqlite3
from contextlib import contextmanager


def test_session_validation_cache_is_bounded_and_validator_scoped(monkeypatch):
    from backend.app import auth

    auth._session_validation_cache.clear()
    calls = []

    async def fake_to_thread(function, *args):
        return function(*args)

    monkeypatch.setattr(auth.asyncio, "to_thread", fake_to_thread)
    monkeypatch.setattr(auth, "_session_digest_valid", lambda _digest: True)

    def validator_one(digest: str) -> bool:
        calls.append(("one", digest))
        return True

    def validator_two(digest: str) -> bool:
        calls.append(("two", digest))
        return False

    async def run() -> None:
        assert await auth._session_digest_valid_cached("same", validator=validator_one) is True
        assert await auth._session_digest_valid_cached("same", validator=validator_one) is True
        assert await auth._session_digest_valid_cached("same", validator=validator_two) is False

    asyncio.run(run())
    assert calls == [("one", "same"), ("two", "same")]

    # Exercise the real insertion/eviction path with a deterministic worker.
    auth._session_validation_cache.clear()

    async def fill_cache() -> None:
        for index in range(auth._SESSION_CACHE_MAX_ENTRIES + 20):
            await auth._session_digest_valid_cached(f"digest-{index}")

    asyncio.run(fill_cache())
    assert len(auth._session_validation_cache) == auth._SESSION_CACHE_MAX_ENTRIES
    assert ("digest-0", id(auth._session_digest_valid)) not in auth._session_validation_cache
    auth._session_validation_cache.clear()


def test_uid_masking_uses_token_boundaries_and_longest_registered_uid():
    from backend.app.privacy import _mask_uid_payload

    payload = {
        "uid": "A1B2C3D4",
        "message": "A1B2C3D4 A1B2C3D4EE interface FACE 2026-11-12",
    }
    result = _mask_uid_payload(
        payload,
        known_uids_provider=lambda: {"A1B2C3D4", "A1B2C3D4EE", "FACE"},
    )
    assert result["uid"] == "****C3D4"
    assert result["message"] == "****C3D4 ******D4EE interface **** 2026-11-12"


def test_telegram_lease_uses_database_clock_and_rejects_expired_renewal():
    from backend.app.telegram.persistence_delivery import build_delivery_callbacks

    connection = sqlite3.connect(":memory:")
    connection.execute(
        "CREATE TABLE telegram_instance_lease "
        "(lease_name TEXT PRIMARY KEY, owner TEXT NOT NULL, expires_at REAL NOT NULL)"
    )

    class Backend:
        @staticmethod
        @contextmanager
        def db_session():
            try:
                yield connection
                connection.commit()
            except Exception:
                connection.rollback()
                raise

        @staticmethod
        def now_business():
            return "2026-11-12T00:00:00"

    callbacks = build_delivery_callbacks(Backend())
    lease = callbacks["lease"]

    assert lease("acquire", "owner-a", 60) is True
    assert lease("renew", "owner-a", 60) is True
    assert lease("renew", "owner-b", 60) is False

    connection.execute(
        "UPDATE telegram_instance_lease SET expires_at=0 WHERE lease_name='bot'"
    )
    connection.commit()
    assert lease("renew", "owner-a", 60) is False
    assert lease("acquire", "owner-b", 60) is True
    connection.close()
