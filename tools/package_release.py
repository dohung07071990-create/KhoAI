#!/usr/bin/env python3
"""Build a clean source ZIP and validate it before returning success."""
from __future__ import annotations

import argparse
import sys
import zipfile
from pathlib import Path

try:
    from .validate_release_archive import validate
except ImportError:  # direct script execution
    from validate_release_archive import validate

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_PARTS = {".git", ".venv", "__pycache__", ".pytest_cache", "camera_evidence", "data"}
EXCLUDED_FILES = {
    "yolov8n.pt",
}


def package(destination: Path) -> None:
    destination = destination.resolve()
    try:
        destination.relative_to(ROOT.resolve())
    except ValueError:
        pass
    else:
        raise ValueError("File ZIP đầu ra phải nằm ngoài thư mục mã nguồn KhoAI.")
    if destination.name.startswith("--"):
        raise ValueError("Tên file đầu ra không được bắt đầu bằng '--'.")
    if destination.suffix.lower() != ".zip":
        raise ValueError("File đầu ra phải có phần mở rộng .zip.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    root_name = f"KhoAI_v{(ROOT / 'VERSION.txt').read_text(encoding='utf-8').strip()}"
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=8) as archive:
        for source in sorted(ROOT.rglob("*")):
            if not source.is_file() or source == destination:
                continue
            relative = source.relative_to(ROOT)
            if any(part.lower() in EXCLUDED_PARTS for part in relative.parts):
                continue
            if relative.as_posix().lower() in EXCLUDED_FILES:
                continue
            if source.suffix.lower() in {".pyc", ".pyo"}:
                continue
            # Ship only the report for this release, not historical dev reports.
            if (source.name.startswith("TEST_REPORT_v") and
                    source.name != f"TEST_REPORT_v{(ROOT / 'VERSION.txt').read_text(encoding='utf-8').strip()}.txt"):
                continue
            if relative == Path("ai/zone.json") or source.name.lower().endswith((
                ".sqlite", ".sqlite3", ".db", ".sqlite-wal", ".sqlite-shm",
                ".sqlite3-wal", ".sqlite3-shm", ".db-wal", ".db-shm"
            )):
                continue
            if source.name == ".env":
                continue
            archive.write(source, Path(root_name) / relative)
    problems = validate(str(destination))
    if problems:
        destination.unlink(missing_ok=True)
        raise RuntimeError("Release validation failed:\n" + "\n".join(problems))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build and validate a KhoAI release ZIP.")
    parser.add_argument("output", help="Output ZIP path; must be outside the source directory.")
    args = parser.parse_args(argv)
    try:
        package(Path(args.output))
    except (OSError, ValueError, RuntimeError) as exc:
        parser.error(str(exc))
    print(f"Release package created and validated: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
