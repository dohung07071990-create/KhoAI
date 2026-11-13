from __future__ import annotations

import pytest
from fastapi import HTTPException

from backend.app.security_credentials import (
    _credential_matches, _hash_password, _verify_password, _validate_admin_secret,
)
from backend.app.session_tokens import _session_digest
from backend.app.uid_normalization import normalize_uid


def test_credential_comparison_and_password_hash_roundtrip():
    assert _credential_matches("mật-khẩu", "mật-khẩu")
    assert not _credential_matches("mật-khẩU", "mật-khẩu")
    encoded = _hash_password("KhoAI-test-password")
    assert _verify_password("KhoAI-test-password", encoded)
    assert not _verify_password("wrong-password", encoded)


def test_admin_secret_policy_rejects_sample_and_accepts_long_secret():
    with pytest.raises(HTTPException):
        _validate_admin_secret("replace_with_a_sample_secret_value")
    _validate_admin_secret("a-unique-production-admin-token-0123456789")


def test_session_digest_and_uid_normalization():
    assert _session_digest(None) is None
    assert _session_digest("session-cookie") == _session_digest("session-cookie")
    assert _session_digest("session-cookie") != "session-cookie"
    assert normalize_uid(" ab:cd-12 ") == "ABCD12"
    with pytest.raises(HTTPException):
        normalize_uid("not-a-uid")
