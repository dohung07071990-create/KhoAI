from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.app import auth, device_auth


def _request(ip: str = "192.0.2.10"):
    return SimpleNamespace(client=SimpleNamespace(host=ip))


def test_auth_facade_reexports_device_auth_dependency():
    assert auth.require_device_key is device_auth.require_device_key
    assert auth._valid_device_secret is device_auth._valid_device_secret


def test_device_auth_fails_closed_when_key_is_not_configured(monkeypatch):
    monkeypatch.setenv("KHOAI_API_KEY", "change-me")
    with pytest.raises(HTTPException) as exc:
        device_auth.require_device_key(_request(), "change-me")
    assert exc.value.status_code == 503


def test_device_auth_rejects_wrong_key_and_throttles(monkeypatch):
    monkeypatch.setenv("KHOAI_API_KEY", "A" * 40)
    monkeypatch.setattr(device_auth, "DEVICE_KEY_FAIL_LIMIT", 3)
    device_auth._device_key_failures.clear()
    ip = "192.0.2.11"
    for _ in range(3):
        with pytest.raises(HTTPException) as exc:
            device_auth.require_device_key(_request(ip), "wrong")
        assert exc.value.status_code == 401
    with pytest.raises(HTTPException) as exc:
        device_auth.require_device_key(_request(ip), "wrong")
    assert exc.value.status_code == 429
    device_auth._device_key_failures.pop(ip, None)


def test_device_auth_accepts_valid_key_and_clears_failure_counter(monkeypatch):
    key = "B" * 40
    monkeypatch.setenv("KHOAI_API_KEY", key)
    ip = "192.0.2.12"
    device_auth._device_key_failures[ip] = [1.0]
    device_auth.require_device_key(_request(ip), key)
    assert ip not in device_auth._device_key_failures
