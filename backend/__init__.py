"""Gói backend của KhoAI.

Phần khởi tạo (init): nạp `.env` ngay khi gói được import, trước khi
`backend.app.main` đọc DB_PATH, BUSINESS_TIMEZONE, CAMERA_INDEX...
"""
from __future__ import annotations

__version__ = "0.3.0"

try:  # `ai/` là tùy chọn (Docker bản nhẹ có thể không kèm theo)
    from ai.envfile import load_env_file

    load_env_file()
except Exception:  # noqa: BLE001 - không để lỗi cấu hình làm hỏng việc import backend
    pass
