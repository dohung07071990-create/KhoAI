from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.app.services.camera_access_policy import CameraAccessPolicy


class Detector:
    def __init__(self, running=False):
        self.running = running
        self.starts = 0

    def start(self):
        self.starts += 1
        self.running = True


def request_with_role(role):
    return SimpleNamespace(state=SimpleNamespace(khoai_role=role))


def test_admin_read_starts_detector():
    detector = Detector()
    CameraAccessPolicy().ensure_camera_for_read(request_with_role("admin"), detector)
    assert detector.starts == 1
    assert detector.running is True


def test_non_admin_read_does_not_start_stopped_detector():
    detector = Detector()
    with pytest.raises(HTTPException) as error:
        CameraAccessPolicy().ensure_camera_for_read(request_with_role("user"), detector)
    assert error.value.status_code == 503
    assert detector.starts == 0
    assert detector.running is False


def test_non_admin_read_can_use_already_running_detector():
    detector = Detector(running=True)
    CameraAccessPolicy().ensure_camera_for_read(request_with_role("user"), detector)
    assert detector.starts == 0
    assert detector.running is True


def test_missing_role_is_not_allowed_to_start_detector():
    detector = Detector()
    with pytest.raises(HTTPException) as error:
        CameraAccessPolicy().ensure_camera_for_read(request_with_role(None), detector)
    assert error.value.status_code == 503
    assert detector.starts == 0
