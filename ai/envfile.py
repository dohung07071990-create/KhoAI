"""Nạp file .env bằng thư viện chuẩn (không cần python-dotenv).

Trước đây `.env.example` có nhưng KHÔNG có đoạn code nào đọc `.env`, nên đặt
`CAMERA_INDEX=1` trong .env không có tác dụng. Hàm này được gọi trong
`ai/__init__.py` và `backend/__init__.py` để mọi cấu hình có hiệu lực ngay từ đầu.

Biến môi trường đã có sẵn trong shell luôn được ưu tiên hơn giá trị trong .env.
"""
from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _parse_line(line: str) -> tuple[str, str] | None:
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    if line.lower().startswith("export "):
        line = line[7:].lstrip()
    if "=" not in line:
        return None
    key, value = line.split("=", 1)
    key, value = key.strip(), value.strip()
    if not key or not key.replace("_", "").isalnum():
        return None
    if value[:1] in {'"', "'"} and value.endswith(value[:1]) and len(value) >= 2:
        value = value[1:-1]
    elif " #" in value:  # comment cuối dòng với giá trị không có ngoặc
        value = value.split(" #", 1)[0].rstrip()
    return key, value


def load_env_file(path: str | os.PathLike[str] | None = None, override: bool = False) -> list[str]:
    """Đọc file .env; trả về danh sách tên biến đã nạp."""
    candidates = [Path(path)] if path else [PROJECT_ROOT / ".env", Path.cwd() / ".env"]
    loaded: list[str] = []
    seen: set[Path] = set()
    for candidate in candidates:
        try:
            candidate = candidate.resolve()
        except OSError:
            continue
        if candidate in seen or not candidate.is_file():
            continue
        seen.add(candidate)
        try:
            text = candidate.read_text(encoding="utf-8-sig")  # utf-8-sig: chịu được BOM của Notepad
        except OSError:
            continue
        for raw in text.splitlines():
            parsed = _parse_line(raw)
            if parsed is None:
                continue
            key, value = parsed
            if override or key not in os.environ:
                os.environ[key] = value
                loaded.append(key)
    return loaded
