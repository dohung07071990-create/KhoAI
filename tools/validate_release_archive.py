#!/usr/bin/env python3
"""Fail closed when a release archive contains runtime data or credentials."""
from __future__ import annotations

import re
import sys
import zipfile
from pathlib import PurePosixPath

FORBIDDEN_PARTS = {"camera_evidence", "data", "__pycache__", ".pytest_cache", ".git",
                   ".mypy_cache", ".ruff_cache", ".tox", ".venv"}
SECRET_PATTERNS = [
    re.compile(rb"(?i)KHOAI_ADMIN_TOKEN\s*=\s*[^\r\n#]{8,}"),
    re.compile(rb"(?i)(?:api[_-]?key|secret|password)\s*[:=]\s*['\"]?[A-Za-z0-9_./+=-]{16,}"),
    re.compile(rb"(?i)(?:sk-[A-Za-z0-9]{20,}|gh[pousr]_[A-Za-z0-9]{20,})"),
]


def validate(path: str) -> list[str]:
    errors: list[str] = []
    with zipfile.ZipFile(path) as archive:
        for info in archive.infolist():
            name = info.filename.replace("\\", "/")
            parts = PurePosixPath(name).parts
            lowered = name.lower()
            if any(part.lower() in FORBIDDEN_PARTS for part in parts):
                errors.append(f"runtime/cache path: {name}")
            if PurePosixPath(lowered).suffix in {".pyc", ".pyo"}:
                errors.append(f"compiled Python bytecode: {name}")
            # Reject SQLite files at any depth, including archives with a project
            # root directory and SQLite WAL/SHM sidecars.
            database_suffixes = (".sqlite", ".sqlite3", ".db", ".sqlite-wal",
                                 ".sqlite-shm", ".sqlite3-wal", ".sqlite3-shm",
                                 ".db-wal", ".db-shm")
            if lowered.endswith(database_suffixes):
                errors.append(f"database file: {name}")
            image_suffix = PurePosixPath(lowered).suffix in {".jpg", ".jpeg", ".png", ".webp"}
            if image_suffix and any("evidence" in part.lower() for part in parts):
                errors.append(f"evidence image: {name}")
            if name.endswith("/.env") or name == ".env":
                errors.append(f"live environment file: {name}")
            # A source release must not carry another archive as an opaque payload.
            if PurePosixPath(lowered).suffix in {".zip", ".7z", ".rar", ".tar", ".gz", ".bz2", ".xz"}:
                errors.append(f"nested archive: {name}")
            if not info.is_dir() and info.file_size >= 4:
                with archive.open(info) as member:
                    if member.read(4) == b"PK\x03\x04":
                        errors.append(f"nested archive signature: {name}")
            if name.endswith("/ai/zone.json") or name == "ai/zone.json":
                errors.append(f"runtime zone configuration: {name}")
            if info.is_dir() or info.file_size > 5_000_000 or name.endswith("tools/validate_release_archive.py"):
                continue
            payload = archive.read(info)
            if name.endswith(".env.example"):
                payload = re.sub(rb"(?im)^KHOAI_ADMIN_TOKEN\s*=.*$", b"KHOAI_ADMIN_TOKEN=", payload)
            for pattern in SECRET_PATTERNS:
                match = pattern.search(payload)
                if not match:
                    continue
                candidate = match.group(0).upper()
                if any(marker in candidate for marker in
                       (b"REPLACE", b"YOUR_", b"THAY", b"CHUOI", b"EXAMPLE", b"REDACTED", b"CHANGE_ME", b"API-KEY-RIENG")):
                    continue
                errors.append(f"possible credential in: {name}")
                break
    return errors


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python tools/validate_release_archive.py <archive.zip>")
    problems = validate(sys.argv[1])
    if problems:
        print("RELEASE BLOCKED")
        print("\n".join(f"- {item}" for item in problems))
        raise SystemExit(1)
    print("Release archive checks passed")
