"""Authorization policy for read access to the AI camera worker."""
from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Request


class CameraAccessPolicy:
    """Enforce that only an admin read request may start the detector."""

    def ensure_camera_for_read(self, request: Request, detector: Any) -> None:
        if getattr(request.state, "khoai_role", None) == "admin":
            detector.start()
            return
        if not bool(getattr(detector, "running", False)):
            raise HTTPException(
                status_code=503,
                detail=(
                    "Camera AI chưa được quản trị viên khởi động; "
                    "yêu cầu xem không tự khởi chạy worker."
                ),
            )
