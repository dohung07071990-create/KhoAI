"""Opaque session-token digest helpers."""
from __future__ import annotations

import hashlib

def _session_digest(session_id: str | None) -> str | None:
    """Return the SHA-256 lookup key; raw cookie values are never persisted."""
    if not session_id:
        return None
    return hashlib.sha256(session_id.encode("utf-8")).hexdigest()

