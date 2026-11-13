import pytest

from ai.config_profiles import profile_env_default, profile_name, profile_settings


def test_demo_profile_defaults(monkeypatch):
    monkeypatch.delenv("KHOAI_PROFILE", raising=False)
    monkeypatch.delenv("KHOAI_ENTRY_GRACE_SECONDS", raising=False)
    assert profile_name() == "demo"
    settings = profile_settings()
    assert settings["entry_grace_seconds"] == 8
    assert settings["presence_release_seconds"] == 8
    assert settings["rfid_ticket_seconds"] == 20
    assert settings["suspicious_seconds"] == 30
    assert settings["suspicious_approach_count"] == 3
    assert profile_settings()["entry_grace_seconds"] == 8
    assert profile_env_default("KHOAI_ENTRY_GRACE_SECONDS", 8) == 8


def test_strict_profile_defaults_and_explicit_environment_override(monkeypatch):
    monkeypatch.setenv("KHOAI_PROFILE", "strict")
    monkeypatch.delenv("KHOAI_ENTRY_GRACE_SECONDS", raising=False)
    settings = profile_settings()
    assert settings["entry_grace_seconds"] == 5
    assert settings["presence_release_seconds"] == 15
    assert settings["rfid_ticket_seconds"] == 10
    assert settings["suspicious_seconds"] == 20
    assert settings["suspicious_approach_count"] == 2
    assert settings["handover_max_gap_seconds"] == 2.5
    assert settings["handover_match_radius"] < 0.08
    assert settings["handover_exclusion_radius"] > 0.08
    assert profile_env_default("KHOAI_ENTRY_GRACE_SECONDS", 8) == 5
    monkeypatch.setenv("KHOAI_ENTRY_GRACE_SECONDS", "12")
    assert profile_env_default("KHOAI_ENTRY_GRACE_SECONDS", 8) == 8


def test_unknown_profile_is_rejected(monkeypatch):
    monkeypatch.setenv("KHOAI_PROFILE", "unknown")
    with pytest.raises(ValueError, match="demo.*strict"):
        profile_name()
