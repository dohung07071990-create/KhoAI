"""Compatibility facade for the KhoAI API Pydantic schemas.

Schema definitions are grouped by domain; imports from this module remain stable.
"""
from __future__ import annotations

from .schemas_access import (
    CardCreate, CardUpdate, RFIDScan, DeviceHeartbeat, AccessCheck, TrackAssociation,
)

from .schemas_camera import (
    CameraZoneUpdate, CameraAntiTheftUpdate, HomographyCalibrationInput, RFIDEntryROIUpdate,
)

from .schemas_events import (
    SecurityEventInput,
)

from .schemas_admin import (
    AdminLogin, AdminUserCreate, AdminUserUpdate,
)

__all__ = [
    'CardCreate', 'CardUpdate', 'RFIDScan', 'DeviceHeartbeat', 'AccessCheck', 'TrackAssociation', 'CameraZoneUpdate', 'CameraAntiTheftUpdate', 'HomographyCalibrationInput', 'RFIDEntryROIUpdate', 'SecurityEventInput', 'AdminLogin', 'AdminUserCreate', 'AdminUserUpdate',
]
