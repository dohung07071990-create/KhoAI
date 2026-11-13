"""RFID UID canonicalization and validation."""
from __future__ import annotations

import re
from fastapi import HTTPException
from .settings import UID_RE

def normalize_uid(uid: str) -> str:
    normalized = re.sub(r"[\s:-]", "", uid).upper()
    if not UID_RE.fullmatch(normalized):
        raise HTTPException(status_code=422, detail="UID phải gồm 4–20 ký tự hex (0–9, A–F).")
    return normalized
