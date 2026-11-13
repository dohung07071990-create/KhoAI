import json

import numpy as np
import pytest

from ai.homography import (
    HomographyCalibrationError,
    HomographyCalibrationManager,
    compute_homography,
    reprojection_error,
    transform_point,
)


def square():
    image = [(0, 0), (100, 0), (100, 100), (0, 100)]
    floor = [(0, 0), (10, 0), (10, 10), (0, 10)]
    return image, floor


def test_identity_mapping_from_four_correspondences():
    points = [(0, 0), (100, 0), (100, 100), (0, 100)]
    matrix = compute_homography(points, points)
    assert transform_point(matrix, (25, 40)) == pytest.approx((25, 40))


def test_requires_four_correspondences():
    with pytest.raises(HomographyCalibrationError):
        compute_homography([(0, 0), (1, 0), (1, 1)], [(0, 0), (1, 0), (1, 1)])


def test_rejects_non_finite_coordinates():
    with pytest.raises(HomographyCalibrationError):
        compute_homography([(0, 0), (1, 0), (1, 1), (0, 1)],
                           [(0, 0), (1, 0), (1, 1), (float("nan"), 1)])


def test_rejects_collinear_correspondences():
    points = [(0, 0), (1, 1), (2, 2), (3, 3)]
    with pytest.raises(HomographyCalibrationError):
        compute_homography(points, [(0, 0), (1, 0), (2, 0), (3, 0)])


def test_reprojection_error_reports_fit_quality():
    image, floor = square()
    matrix = compute_homography(image, floor)
    assert reprojection_error(matrix, image, floor)["rms"] == pytest.approx(0.0, abs=1e-9)


def test_manager_calibrates_persists_and_maps_only_matching_camera_size(tmp_path):
    image, floor = square()
    manager = HomographyCalibrationManager(tmp_path / "camera.json", "usb_external")
    result = manager.calibrate(image, floor, (640, 480), floor_units="m", max_rms_error=0.01)
    assert result["valid"] is True
    assert manager.transform((50, 50), (640, 480)) == pytest.approx((5, 5))
    assert manager.transform((50, 50), (1280, 720)) is None
    assert manager.status((1280, 720))["reason"] == "image_size_mismatch"
    loaded = HomographyCalibrationManager(tmp_path / "camera.json", "usb_external")
    assert loaded.status((640, 480))["valid"] is True


def test_manager_rejects_excessive_reprojection_error(tmp_path):
    image, floor = square()
    image.append((50, 50))
    floor.append((5, 5.8))
    manager = HomographyCalibrationManager(tmp_path / "camera.json")
    with pytest.raises(HomographyCalibrationError):
        manager.calibrate(image, floor, (640, 480), max_rms_error=0.01)
    assert manager.status()["valid"] is False


def test_invalidate_disables_mapping(tmp_path):
    image, floor = square()
    manager = HomographyCalibrationManager(tmp_path / "camera.json")
    manager.calibrate(image, floor, (640, 480))
    state = manager.invalidate("camera_moved")
    assert state["valid"] is False
    assert state["reason"] == "camera_moved"
    assert manager.transform((50, 50), (640, 480)) is None
    persisted = json.loads((tmp_path / "camera.json").read_text(encoding="utf-8"))
    assert persisted["enabled"] is False


def test_wrong_camera_profile_is_not_used(tmp_path):
    image, floor = square()
    path = tmp_path / "camera.json"
    HomographyCalibrationManager(path, "usb_external").calibrate(image, floor, (640, 480))
    other_camera = HomographyCalibrationManager(path, "another_camera")
    assert other_camera.status((640, 480))["valid"] is False
    assert other_camera.status((640, 480))["reason"] == "camera_id_mismatch"


def test_corrupt_profile_fails_closed(tmp_path):
    path = tmp_path / "camera.json"
    path.write_text('{"enabled": true, "matrix": [1, 2]}', encoding="utf-8")
    manager = HomographyCalibrationManager(path)
    assert manager.status()["valid"] is False
    assert manager.transform((10, 10), (640, 480)) is None


def test_status_exposes_calibrated_floor_bounds_for_visual_mapping(tmp_path):
    image, floor = square()
    manager = HomographyCalibrationManager(tmp_path / "camera.json", "usb_external")
    result = manager.calibrate(image, floor, (640, 480), floor_units="m")
    assert result["floor_bounds"] == {"min_x": 0.0, "max_x": 10.0, "min_y": 0.0, "max_y": 10.0}
