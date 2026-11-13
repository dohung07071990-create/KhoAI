from __future__ import annotations

from backend.app import schemas
from backend.app.schemas_access import CardCreate as SplitCardCreate
from backend.app.schemas_admin import AdminLogin as SplitAdminLogin
from backend.app.schemas_camera import HomographyCalibrationInput as SplitHomographyInput
from backend.app.schemas_events import SecurityEventInput as SplitSecurityEventInput


def test_schema_facade_preserves_public_class_identity():
    assert schemas.CardCreate is SplitCardCreate
    assert schemas.AdminLogin is SplitAdminLogin
    assert schemas.HomographyCalibrationInput is SplitHomographyInput
    assert schemas.SecurityEventInput is SplitSecurityEventInput


def test_schema_facade_exports_all_models():
    expected = {
        "CardCreate", "CardUpdate", "RFIDScan", "DeviceHeartbeat", "AccessCheck",
        "TrackAssociation", "CameraZoneUpdate", "CameraAntiTheftUpdate",
        "HomographyCalibrationInput", "RFIDEntryROIUpdate", "SecurityEventInput",
        "AdminLogin", "AdminUserCreate", "AdminUserUpdate",
    }
    assert set(schemas.__all__) == expected
    assert all(hasattr(schemas, name) for name in expected)


def test_card_create_validation_is_unchanged():
    card = schemas.CardCreate(uid="A1B2", name="Operator", expires_at="2027-01-02", color="#aabbcc")
    assert card.expires_at == "2027-01-02"
    assert card.color == "#aabbcc"
