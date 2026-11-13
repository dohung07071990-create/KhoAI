"""Shared UID redaction helpers for viewer-facing payloads."""
from __future__ import annotations

import logging
import re
import threading
import time
from typing import Any

from .auth import db_session

logger = logging.getLogger("khoai")

def _mask_uid(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    compact = re.sub(r"[^0-9A-Fa-f]", "", value)
    if not compact:
        return value
    if len(compact) <= 4:
        return "****"
    return "*" * (len(compact) - 4) + compact[-4:]


def _mask_uid_fields(value: Any) -> Any:
    """Backward-compatible alias for complete viewer payload redaction."""
    return _mask_uid_payload(value)


_known_uid_cache: tuple[float, set[str]] = (0.0, set())
_known_uid_cache_lock = threading.Lock()


def _known_card_uids_for_redaction() -> set[str]:
    """Return registered card UIDs from a short-lived cache for viewer redaction."""
    global _known_uid_cache
    now = time.monotonic()
    with _known_uid_cache_lock:
        if now - _known_uid_cache[0] < 5.0:
            return set(_known_uid_cache[1])
        try:
            with db_session() as db:
                rows = db.execute("SELECT uid FROM cards WHERE uid IS NOT NULL AND uid != ''").fetchall()
            values = {str(row["uid"]) for row in rows if row["uid"]}
            _known_uid_cache = (time.monotonic(), values)
            return set(values)
        except Exception as exc:
            logger.warning("Không tải được danh sách UID để che cho viewer: %s", type(exc).__name__)
            # Do not cache a database failure; structured UIDs in the payload
            # are still redacted by the caller.
            return set()


def _mask_uid_payload(
    value: Any,
    *,
    known_uids_provider=None,
) -> Any:
    """Mask structured UIDs and known card UIDs in free-text fields.

    UID candidates come only from structured payload fields or the registered
    cards table. No generic hexadecimal regex is applied, so dates, durations,
    Track IDs and ordinary words remain unchanged.
    """
    provider = known_uids_provider or _known_card_uids_for_redaction
    known: set[str] = provider()

    def collect(item: Any) -> None:
        if isinstance(item, dict):
            for key, child in item.items():
                if str(key).lower() in {"uid", "card_uid"} and child:
                    known.add(str(child))
                else:
                    collect(child)
        elif isinstance(item, (list, tuple)):
            for child in item:
                collect(child)

    collect(value)
    # Compile a single alternation for this payload. Longest-first ordering
    # preserves the previous behavior when one registered UID prefixes another.
    uid_by_folded = {uid.casefold(): uid for uid in known if uid}
    ordered = sorted(uid_by_folded.values(), key=len, reverse=True)
    uid_pattern = (
        re.compile(
            r"(?<![0-9A-Za-z])(?:" + "|".join(re.escape(uid) for uid in ordered)
            + r")(?![0-9A-Za-z])",
            re.IGNORECASE,
        )
        if ordered else None
    )
    masked_by_folded = {uid.casefold(): str(_mask_uid(uid)) for uid in ordered}

    def replace_text(text: str) -> str:
        if uid_pattern is None:
            return text
        return uid_pattern.sub(
            lambda match: masked_by_folded.get(match.group(0).casefold(), match.group(0)),
            text,
        )

    def redact(item: Any) -> Any:
        if isinstance(item, dict):
            return {key: (_mask_uid(child) if str(key).lower() in {"uid", "card_uid"} and child
                          else redact(child)) for key, child in item.items()}
        if isinstance(item, list):
            return [redact(child) for child in item]
        if isinstance(item, tuple):
            return tuple(redact(child) for child in item)
        if isinstance(item, str):
            return replace_text(item)
        return item

    return redact(value)
