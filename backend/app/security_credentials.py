"""Credential comparison, password hashing and administrator-secret policy."""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from fastapi import HTTPException

def _credential_matches(supplied: str | None, expected: str) -> bool:
    """Compare UTF-8 credentials safely, including non-ASCII input."""
    if supplied is None:
        return False
    try:
        return hmac.compare_digest(supplied.encode("utf-8"), expected.encode("utf-8"))
    except (AttributeError, UnicodeError):
        return False


def _hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    rounds = 600_000
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, rounds)
    return f"pbkdf2_sha256${rounds}$" + base64.urlsafe_b64encode(salt).decode() + "$" + base64.urlsafe_b64encode(digest).decode()


def _verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, rounds, salt_text, digest_text = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256": return False
        iterations = int(rounds)
        if iterations < 100_000 or iterations > 2_000_000: return False
        salt = base64.urlsafe_b64decode(salt_text.encode())
        expected = base64.urlsafe_b64decode(digest_text.encode())
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False



def _validate_admin_secret(expected: str) -> None:
    sample_markers = ("thay-bang", "change-me", "changeme", "your-secret", "example-token", "replace_with")
    if len(expected) < 24 or any(marker in expected.lower() for marker in sample_markers):
        raise HTTPException(status_code=503, detail="KHOAI_ADMIN_TOKEN phải là chuỗi bí mật riêng dài ít nhất 24 ký tự; không dùng giá trị mẫu.")
