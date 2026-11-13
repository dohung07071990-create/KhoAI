
"""Validated planar image-pixel -> warehouse-floor XY calibration.

Coordinates are unavailable unless a real, camera-specific calibration is enabled.
A matching resolution alone cannot prove that a physical camera has not moved.
"""

from __future__ import annotations

import json
import math
import os
import uuid

from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any, Sequence

import cv2
import numpy as np
from numpy.typing import ArrayLike


class HomographyCalibrationError(ValueError):
    pass


def _points(values: ArrayLike,name: str,minimum: int = 4) -> np.ndarray:
    arr = np.asarray(values, dtype=np.float64)
    if arr.ndim != 2 or arr.shape[1] != 2 or len(arr) < minimum:
        raise HomographyCalibrationError(f"{name}: cần ít nhất {minimum} cặp tọa độ (x, y).")
    if not np.isfinite(arr).all():
        raise HomographyCalibrationError(f"{name}: tọa độ phải là số hữu hạn.")
    return arr


def compute_homography(image_points: ArrayLike,floor_points: ArrayLike) -> np.ndarray:
    src = _points(image_points, "image_points")
    dst = _points(floor_points, "floor_points")
    if src.shape != dst.shape:
        raise HomographyCalibrationError("Số cặp điểm ảnh và điểm sàn phải bằng nhau.")

    # Reject degenerate/collinear point sets.
    if (
        np.linalg.matrix_rank(src - src.mean(axis=0)) < 2
        or np.linalg.matrix_rank(dst - dst.mean(axis=0)) < 2
    ):
        raise HomographyCalibrationError("Các điểm hiệu chuẩn không được thẳng hàng hoặc suy biến.")
    matrix, _ = cv2.findHomography(src, dst, method=0)
    if (
        matrix is None
        or not np.isfinite(matrix).all()
        or np.linalg.matrix_rank(matrix) < 3
    ):
        raise HomographyCalibrationError("Không thể tính Homography từ các điểm đã cung cấp.")
    if abs(matrix[2, 2]) > 1e-12:
        matrix = matrix / matrix[2, 2]
    return matrix


def transform_point(matrix: ArrayLike,image_point: ArrayLike) -> tuple[float, float]:
    h = np.asarray(matrix, dtype=np.float64)
    p = np.asarray(image_point, dtype=np.float64)
    if (
        h.shape != (3, 3)
        or p.shape != (2,)
        or not np.isfinite(h).all()
        or not np.isfinite(p).all()
    ):
        raise HomographyCalibrationError("Ma trận hoặc điểm đầu vào không hợp lệ.")
    mapped = h @ np.array([p[0], p[1], 1.0])
    if abs(mapped[2]) < 1e-10:
        raise HomographyCalibrationError("Điểm nằm tại vô cực của phép chiếu.")
    result = mapped[:2] / mapped[2]
    if not np.isfinite(result).all():
        raise HomographyCalibrationError("Phép chiếu tạo tọa độ không hữu hạn.")
    return float(result[0]), float(result[1])


def reprojection_error(matrix: ArrayLike,image_points: ArrayLike,floor_points: ArrayLike) -> dict[str, float]:
    src = _points(image_points, "image_points")
    dst = _points(floor_points, "floor_points")
    if src.shape != dst.shape:
        raise HomographyCalibrationError("Số cặp điểm ảnh và điểm sàn phải bằng nhau.")
    projected = np.asarray([transform_point(matrix, point) for point in src],dtype=np.float64)
    errors = np.linalg.norm(projected - dst, axis=1)
    return {"rms": float(math.sqrt(float(np.mean(errors ** 2)))),"max": float(np.max(errors)),"mean": float(np.mean(errors))}


class HomographyCalibrationManager:

    def __init__(self,path: str | Path,camera_id: str = "usb_external") -> None:
        self.path = Path(path)
        self.camera_id = str(camera_id)
        self._lock = RLock()
        self._profile: dict[str, Any] | None = None
        self._load()

    def _load(self) -> None:
        with self._lock:
            if not self.path.is_file():
                self._profile = None
                return
            try:
                data = json.loads(
                    self.path.read_text(encoding="utf-8")
                )
                if not isinstance(data, dict):
                    raise ValueError("Cấu hình calibration phải là JSON object.")
                matrix = np.asarray(data.get("matrix"),dtype=np.float64)
                size = data.get("image_size")
                if (
                    data.get("enabled") is not True
                    or matrix.shape != (3, 3)
                    or not np.isfinite(matrix).all()
                    or np.linalg.matrix_rank(matrix) < 3
                    or not isinstance(size, list)
                    or len(size) != 2
                    or int(size[0]) <= 0
                    or int(size[1]) <= 0
                    or not data.get("camera_id")
                    or not data.get("calibration_id")
                ):
                    raise ValueError("Cấu hình calibration không hợp lệ.")
                self._profile = data
            except Exception as exc:
                self._profile = {"enabled": False,"stale": True,"reason": f"invalid_profile: {exc}"}

    def calibrate(self,image_points: ArrayLike,floor_points: ArrayLike,image_size: Sequence[int],*,floor_units: str = "warehouse_units",max_rms_error: float = 0.15) -> dict[str, Any]:
        if (
            len(image_size) != 2
            or int(image_size[0]) <= 0
            or int(image_size[1]) <= 0
        ):
            raise HomographyCalibrationError("image_size phải là [width, height] hợp lệ.")
        max_error = float(max_rms_error)
        if not math.isfinite(max_error) or max_error <= 0:
            raise HomographyCalibrationError("max_rms_error phải lớn hơn 0.")
        src = _points(image_points, "image_points")
        dst = _points(floor_points, "floor_points")
        matrix: np.ndarray = compute_homography(src, dst)
        error: dict[str, float] = reprojection_error(matrix,src,dst)
        if error["rms"] > max_error:
            raise HomographyCalibrationError(
                f"Sai số RMS {error['rms']:.6g} vượt ngưỡng "
                f"{max_error:.6g} {floor_units}."
            )
        profile: dict[str, Any] = {"enabled": True,"stale": False,"mapping": "planar_xy","camera_id": self.camera_id,"calibration_id": uuid.uuid4().hex,"created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "image_size": [int(image_size[0]),int(image_size[1])],
            "floor_units": (str(floor_units).strip() or "warehouse_units"),
            "point_count": int(len(src)),
            "validation_level": ("fit_only_4_points"
                if len(src) == 4
                else "in_sample_reprojection"),
            "image_points": src.tolist(),
            "floor_points": dst.tolist(),
            "matrix": matrix.tolist(),
            "reprojection_error": error,
            "max_rms_error": max_error
        }
        with self._lock:
            self.path.parent.mkdir(parents=True,exist_ok=True)
            temp = self.path.with_suffix(self.path.suffix + ".tmp")
            temp.write_text(json.dumps(profile,ensure_ascii=False,indent=2),encoding="utf-8")
            os.replace(temp, self.path)
            self._profile = profile
        return self.status(image_size)

    def invalidate(self,reason: str = "operator_invalidated") -> dict[str, Any]:
        with self._lock:
            if self._profile:
                self._profile = {**self._profile,"enabled": False,"stale": True,"reason": str(reason)}
                self.path.parent.mkdir(parents=True,exist_ok=True)
                self.path.write_text(json.dumps(self._profile,ensure_ascii=False,indent=2),encoding="utf-8")
            return self.status()

    def status(self,image_size: Sequence[int] | None = None) -> dict[str, Any]:
        with self._lock:
            p = dict(self._profile or {})
        if not p:
            return {"enabled": False,"valid": False,"reason": "not_calibrated","camera_id": self.camera_id}
        reason = p.get("reason")
        if p.get("camera_id") != self.camera_id:
            reason = "camera_id_mismatch"
        elif (
            image_size is not None
            and list(map(int, image_size)) != p.get("image_size")
        ):
            reason = "image_size_mismatch"
        valid = (
            p.get("enabled") is True
            and not p.get("stale")
            and reason is None
        )
        floor_points = p.get("floor_points") or []
        floor_bounds = None

        try:
            values = np.asarray(floor_points,dtype=np.float64)
            if (
                values.ndim == 2
                and len(values.shape) == 2
                and values.shape[-1] == 2
                and len(values) >= 4
                and np.isfinite(values).all()
            ):
                floor_bounds = {"min_x": float(np.min(values[:, 0])),"max_x": float(np.max(values[:, 0])),"min_y": float(np.min(values[:, 1])),"max_y": float(np.max(values[:, 1]))}
        except (TypeError, ValueError):
            floor_bounds = None
        return {"enabled": bool(p.get("enabled")),"valid": bool(valid),"reason": reason or (None if valid else "invalidated"),"camera_id": p.get("camera_id",self.camera_id),"calibration_id": p.get("calibration_id"),"image_size": p.get("image_size"),"floor_units": p.get("floor_units"),"floor_bounds": floor_bounds,"reprojection_error": p.get("reprojection_error"),"point_count": p.get("point_count"),"validation_level": p.get("validation_level"),"created_at": p.get("created_at")}

    def transform(self,image_point: ArrayLike,image_size: Sequence[int]) -> tuple[float, float] | None:
        state = self.status(image_size)
        if not state["valid"]:
            return None
        with self._lock:
            profile = self._profile
            matrix = (
                profile.get("matrix")
                if profile is not None
                else None
            )
        if matrix is None:
            return None
        return transform_point(matrix, image_point)
