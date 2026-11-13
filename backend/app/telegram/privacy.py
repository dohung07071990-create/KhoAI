"""Telegram-specific RFID privacy helpers shared outside the API module."""
from __future__ import annotations
import re
from typing import Any


def mask_uid(value: Any) -> str:
    raw = str(value or "")
    if len(raw) <= 4:
        return "****"
    return "****" + raw[-4:]


def collect_uids(value: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).lower() in {"uid", "card_uid"} and item:
                found.add(str(item))
            else:
                found.update(collect_uids(item))
    elif isinstance(value, (list, tuple)):
        for item in value:
            found.update(collect_uids(item))
    return found


_NAME_KEYS = {"person_name", "cardholder_name", "operator_name", "name"}


def _collect_names(value: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).lower() in _NAME_KEYS and item:
                found.add(str(item))
            else:
                found.update(_collect_names(item))
    elif isinstance(value, (list, tuple)):
        for item in value:
            found.update(_collect_names(item))
    return found


def _mask_uid_fields(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: (mask_uid(item) if str(key).lower() in {"uid", "card_uid"} and item else _mask_uid_fields(item)) for key, item in value.items()}
    if isinstance(value, list): return [_mask_uid_fields(item) for item in value]
    return value


def _remove_name_fields(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _remove_name_fields(item) for key, item in value.items()
                if str(key).lower() not in _NAME_KEYS}
    if isinstance(value, list):
        return [_remove_name_fields(item) for item in value]
    return value


def _mask_uid_mentions(message: str, uids: set[str]) -> str:
    non_uid_context = r"(?i)(?:track(?:\s*id)?|port|cổng|năm|year|ngày|date|timestamp)\s*(?:#|:|=)?\s*$"
    for uid in sorted((item for item in uids if item), key=len, reverse=True):
        compact = re.sub(r"[^0-9A-Fa-f]", "", uid)
        if len(compact) < 8:
            # Short UIDs overlap with years, port numbers and ordinary counts.
            # Only redact them when the text explicitly labels the value.
            label = r"(?i)(\b(?:card[_ ]?)?uid\s*[:=]?\s*)"
            pattern = re.compile(label + re.escape(uid) + r"(?![0-9A-Fa-f])", re.IGNORECASE)
            message = pattern.sub(lambda match: match.group(1) + mask_uid(uid), message)
            if message.strip().casefold() == uid.casefold():
                message = mask_uid(uid)
            continue
        pattern = re.compile(r"(?<![0-9A-Fa-f])" + re.escape(uid) + r"(?![0-9A-Fa-f])", re.IGNORECASE)
        def redact_known(match: re.Match[str]) -> str:
            prefix = message[max(0, match.start() - 24):match.start()]
            return match.group(0) if re.search(non_uid_context, prefix) else mask_uid(uid)
        message = pattern.sub(redact_known, message)

    # Also catch common byte-pair formatting such as A1:B2:C3:D4 or
    # A1 B2 C3 D4. Require at least four bytes so dates and short counters
    # are not treated as card identifiers.
    formatted_uid = re.compile(
        r"(?<![0-9A-Fa-f])([0-9A-Fa-f]{2}(?:[:\s]+[0-9A-Fa-f]{2}){3,9})(?![0-9A-Fa-f])"
    )

    def redact_formatted(match: re.Match[str]) -> str:
        prefix = message[max(0, match.start() - 24):match.start()]
        if re.search(non_uid_context, prefix):
            return match.group(0)
        compact = re.sub(r"[^0-9A-Fa-f]", "", match.group(1))
        return mask_uid(compact)

    message = formatted_uid.sub(redact_formatted, message)

    # An explicit UID label is sufficient evidence even for short valid RFID
    # identifiers, which the generic free-text fallback intentionally avoids.
    labeled_uid = re.compile(r"(?i)(\b(?:card[_ ]?)?uid\s*[:=]?\s*)([0-9A-F]{4,20})(?![0-9A-F])")
    message = labeled_uid.sub(lambda match: match.group(1) + mask_uid(match.group(2)), message)

    # Fallback for identifiers that were written only into free text and were
    # not present in event details or the current card table. Restrict matches
    # to common RFID UID hex lengths; ordinary years and short counters survive.
    fallback = re.compile(r"(?<![0-9A-Fa-f])[0-9A-Fa-f]{8,20}(?![0-9A-Fa-f])")

    def redact_candidate(match: re.Match[str]) -> str:
        candidate = match.group(0)
        if re.search(non_uid_context, message[max(0, match.start() - 24):match.start()]):
            return candidate
        return mask_uid(candidate)

    return fallback.sub(redact_candidate, message)


def mask_telegram_event(event: dict[str, Any], known_uids: set[str] | None = None,
                        known_names: set[str] | None = None,
                        include_person_name: bool = False) -> dict[str, Any]:
    result = dict(event)
    details = result.get("details")
    if details is None and isinstance(result.get("details_json"), str):
        import json
        try:
            details = json.loads(result["details_json"] or "{}")
        except (TypeError, ValueError):
            details = {}
    uids = set(known_uids or ()) | collect_uids(details or {})
    result["message"] = _mask_uid_mentions(str(result.get("message") or ""), uids)
    message = str(result.get("message") or "")
    if not include_person_name:
        names = set(known_names or ()) | _collect_names(details or {})
        for name in sorted((n for n in names if n), key=len, reverse=True):
            message = re.sub(r"(?<!\w)" + re.escape(name) + r"(?!\w)", "[đã ẩn danh tính]", message, flags=re.IGNORECASE)
        details = _remove_name_fields(details or {})
    result["message"] = message
    if details is not None:
        result["details"] = _mask_uid_fields(details)
    result.pop("details_json", None)
    return result
