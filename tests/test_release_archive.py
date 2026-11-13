"""Release validator must detect runtime data regardless of ZIP root layout."""
from pathlib import Path
import zipfile

from tools.validate_release_archive import validate


def _zip(path: Path, members: dict[str, bytes]) -> Path:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in members.items():
            archive.writestr(name, content)
    return path


def test_validator_detects_sqlite_with_project_root(tmp_path):
    archive = _zip(tmp_path / "rooted.zip", {
        "KhoAI_v0.6.2/data/khoai.sqlite3": b"SQLite format 3\x00",
    })
    errors = validate(str(archive))
    assert any("database file" in error for error in errors), errors


def test_validator_detects_nested_sqlite_and_wal_without_project_root(tmp_path):
    archive = _zip(tmp_path / "nested.zip", {
        "backup/runtime/store.DB": b"db",
        "data/khoai.sqlite3-wal": b"wal",
    })
    errors = validate(str(archive))
    assert sum("database file" in error for error in errors) == 2, errors


def test_validator_detects_evidence_images_with_root_and_case_variants(tmp_path):
    archive = _zip(tmp_path / "evidence.zip", {
        "KhoAI_v0.6.2/Data/Camera_Evidence/IMG_001.JPG": b"image",
    })
    errors = validate(str(archive))
    assert any("evidence image" in error for error in errors), errors


def test_validator_accepts_clean_archive_with_project_root(tmp_path):
    archive = _zip(tmp_path / "clean.zip", {
        "KhoAI_v0.6.2/README.md": b"clean",
        "KhoAI_v0.6.2/ai/zone.json.example": b"{}",
    })
    assert validate(str(archive)) == []



def test_validator_rejects_runtime_data_folder_even_without_database(tmp_path):
    archive = _zip(tmp_path / "runtime-data.zip", {
        "KhoAI_v0.6.2/data/rfid_entry_roi.json": b'{"points": []}',
        "KhoAI_v0.6.2/data/decision_replay.jsonl": b'{"kind":"decision_frame"}',
    })
    errors = validate(str(archive))
    assert sum("runtime/cache path" in error for error in errors) == 2, errors


def test_validator_rejects_nested_zip_archive(tmp_path):
    archive = _zip(tmp_path / "nested-archive.zip", {
        "KhoAI_v0.6.2/README.md": b"clean",
        "KhoAI_v0.6.2/old-build.zip": b"PK\x03\x04opaque",
    })
    errors = validate(str(archive))
    assert any("nested archive" in error for error in errors), errors


def test_validator_rejects_zip_payload_even_without_zip_extension(tmp_path):
    archive = _zip(tmp_path / "nested-signature.zip", {
        "KhoAI_v0.6.2/old-build.bin": b"PK\x03\x04opaque",
    })
    errors = validate(str(archive))
    assert any("nested archive signature" in error for error in errors), errors


def test_package_cli_help_is_not_treated_as_output(tmp_path):
    import subprocess
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, str(root / "tools" / "package_release.py"), "--help"],
        cwd=root, capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0
    assert "usage:" in result.stdout.lower()
    assert not (root / "--help").exists()


def test_package_rejects_destination_inside_source_tree(tmp_path):
    import pytest
    from tools.package_release import ROOT, package

    with pytest.raises(ValueError, match="ngoài thư mục mã nguồn"):
        package(ROOT / "accidental.zip")
    assert not (ROOT / "accidental.zip").exists()


def test_release_package_includes_only_current_test_report(tmp_path):
    from tools.package_release import ROOT, package

    output = tmp_path / "release.zip"
    package(output)
    with zipfile.ZipFile(output) as archive:
        names = archive.namelist()
    reports = [Path(name).name for name in names if Path(name).name.startswith("TEST_REPORT_v")]
    assert reports == [f"TEST_REPORT_v{(ROOT / 'VERSION.txt').read_text(encoding='utf-8').strip()}.txt"]
