"""KhoAI vision pipeline: camera USB -> YOLO person + ByteTrack -> luật vùng cấm.

Pipeline camera USB ngoài; các quyết định an ninh do Decision Engine quản lý.

CAMERA
  * Bản cũ chỉ đọc camera khi có người mở luồng /stream, nhưng giao diện chỉ mở luồng khi
    `usb_available` = True, mà `usb_available` chỉ True sau khi đã đọc camera => vòng lặp chết,
    camera không bao giờ được mở từ dashboard. Giờ có luồng nền tự mở camera (start()).
  * Dò camera tự động (ưu tiên camera USB ngoài), thử nhiều backend, bỏ frame khởi động.
  * 1 luồng đọc camera liên tục (luôn lấy frame mới nhất, không bị trễ) + 1 luồng chạy AI;
    nhiều trình duyệt xem cùng lúc không còn làm AI chạy lặp và rối ID.

VÙNG CẤM
  * Người không có track ID (ByteTrack chưa gán) trước đây bị bỏ qua hoàn toàn -> không báo đỏ.
  * Người đứng sát camera bị cắt chân ở đáy khung: điểm chân = đáy khung hình nằm NGOÀI đa giác
    -> không báo đỏ dù cả người ở trong vùng. Giờ dò thêm phần thân dưới khi chân bị cắt.
  * Vẽ vùng/nhãn lên frame TRƯỚC khi đưa cho YOLO -> đã đổi: AI nhìn frame sạch, vẽ sau.
  * Hysteresis vào/ra vùng dùng thời gian thực (giây), không phụ thuộc FPS.
  * Box nhỏ vô lý (ghế, bóng, vật thể bị nhận nhầm là người) bị lọc theo chiều cao tối thiểu.
  * draw_zone.py vẽ ở độ phân giải gốc của camera còn detector ép 640x480 -> lệch khung nhìn.
    Giờ dùng chung một hàm mở camera và lưu kèm kích thước khung (frame_size) để cảnh báo khi lệch.
  * File zone.json được nạp lại tự động khi thay đổi (bản cũ chỉ đọc lúc khởi động).

Track ID là ID theo dõi tạm thời, không phải danh tính. RFID ticket chỉ tự ghép trong ROI cửa đã cấu hình và khi không mơ hồ; nếu không đủ điều kiện, cần liên kết thủ công. Handover ID là heuristic không sinh trắc học.
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
import uuid
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence
from zoneinfo import ZoneInfo

import cv2
import numpy as np

from .camera_utils import AUTO, OpenedCamera, open_camera, parse_camera_source
from .decision import DecisionConfig, DecisionEngine
from .homography import HomographyCalibrationManager
from .config_profiles import profile_env_default, profile_name

logger = logging.getLogger(__name__)
AI_DIR = Path(__file__).resolve().parent
ZONE_FILE = Path(os.getenv("KHOAI_ZONE_FILE", str(AI_DIR / "zone.json")))
BUSINESS_TZ = ZoneInfo(os.getenv("BUSINESS_TIMEZONE", "Asia/Ho_Chi_Minh"))
DEFAULT_ZONE: tuple[tuple[float, float], ...] = (
    (0.20, 0.40), (0.80, 0.40), (0.95, 0.95), (0.05, 0.95),
)
MAX_EVENTS = 100
EVIDENCE_DIR = Path(os.getenv("KHOAI_CAMERA_EVIDENCE_DIR", str(AI_DIR.parent / "data" / "camera_evidence")))
HEATMAP_WIDTH = 80
HEATMAP_HEIGHT = 60


def _env_float(name: str, default: float, minimum: float = 0.0) -> float:
    default = profile_env_default(name, default)
    try:
        return max(minimum, float(os.getenv(name, str(default))))
    except ValueError:
        return default


def _env_int(name: str, default: int, minimum: int = 0) -> int:
    return int(_env_float(name, default, minimum))


HEATMAP_HALF_LIFE_SECONDS = _env_float("KHOAI_HEATMAP_HALF_LIFE", 45.0, 5.0)


DWELL_SECONDS = _env_float("KHOAI_DWELL_SECONDS", 30.0, 1.0)
CONFIDENCE = min(0.95, max(0.1, _env_float("KHOAI_CONFIDENCE", 0.35)))
IMAGE_SIZE = _env_int("KHOAI_IMAGE_SIZE", 640, 320)
FRAME_WIDTH = _env_int("KHOAI_FRAME_WIDTH", 640, 320)
FRAME_HEIGHT = _env_int("KHOAI_FRAME_HEIGHT", 480, 240)
STREAM_FPS = min(30, max(8, _env_int("KHOAI_STREAM_FPS", 20, 8)))
STREAM_JPEG_QUALITY = min(90, max(55, _env_int("KHOAI_STREAM_JPEG_QUALITY", 74, 55)))
CAMERA_FOURCC = os.getenv("KHOAI_CAMERA_FOURCC", "MJPG").strip().upper() or None
if CAMERA_FOURCC in {"NONE", "OFF", "0"}:
    CAMERA_FOURCC = None
AI_DEVICE = os.getenv("KHOAI_AI_DEVICE", "cpu")
YOLO_WEIGHTS = os.getenv("KHOAI_YOLO_MODEL", "yolov8n.pt")

# Luật xác định "người ở trong vùng"
ZONE_MODE = os.getenv("KHOAI_ZONE_MODE", "foot").strip().lower()  # foot | center | overlap
if ZONE_MODE not in {"foot", "center", "overlap"}:
    ZONE_MODE = "foot"
ZONE_OVERLAP_MIN = min(1.0, _env_float("KHOAI_ZONE_OVERLAP", 0.30))        # chỉ dùng cho mode overlap
TRUNCATED_FALLBACK = os.getenv("KHOAI_TRUNCATED_FALLBACK", "1") != "0"      # xử lý chân bị cắt ở đáy khung
ENTER_CONFIRM_SECONDS = _env_float("KHOAI_ENTER_CONFIRM_SECONDS", 0.10, 0.0)
EXIT_CONFIRM_SECONDS = _env_float("KHOAI_EXIT_CONFIRM_SECONDS", 0.20, 0.0)
ZONE_EXIT_BUFFER_RATIO = _env_float("KHOAI_ZONE_EXIT_BUFFER_RATIO", 0.02, 0.0)
MIN_BOX_HEIGHT_RATIO = _env_float("KHOAI_MIN_BOX_HEIGHT", 0.08)  # lọc box quá nhỏ (tỉ lệ chiều cao khung)
# Quyền gắn với Track có TTL ngắn; cần quẹt/xác nhận lại để gia hạn.
AUTH_MAX_SECONDS = min(60.0, _env_float("KHOAI_AUTH_MAX_SECONDS", 60.0, 5.0))
CAMERA_FRAME_STALE_SECONDS = 3.0
# Camera is considered stable only after a continuous run of fresh frames.
CAMERA_RECOVERY_STABLE_SECONDS = 1.0
CAMERA_RECOVERY_MAX_FRAME_GAP_SECONDS = 0.50
CAMERA_RECOVERY_MIN_FRAMES = 3
CAMERA_FRAME_HISTORY_SECONDS = 2.0
RFID_AUTO_BIND_ENABLED = os.getenv("KHOAI_RFID_AUTO_BIND_ENABLED", "0").strip().lower() in {"1", "true", "yes", "on"}
RFID_TRACK_OVERLAP_REVOKE_IOU = 0.50
RFID_TRACK_AUTH_LOSS_SECONDS = _env_float("KHOAI_RFID_TRACK_AUTH_LOSS_SECONDS", 0.75, 0.1)
RFID_TICKET_SECONDS = _env_float("KHOAI_RFID_TICKET_SECONDS", 20.0, 1.0)
MAX_PENDING_RFID_TICKETS = min(10000, max(1, _env_int("KHOAI_RFID_MAX_PENDING_TICKETS", 1024, 1)))
RFID_BIND_STABILITY_SECONDS = _env_float("KHOAI_RFID_BIND_STABILITY_SECONDS", 0.30, 0.0)
RFID_BIND_MAX_OBSERVATION_GAP_SECONDS = 0.50
TRACK_HANDOVER_MAX_DISTANCE_PX = _env_float("KHOAI_TRACK_HANDOVER_MAX_DISTANCE_PX", 80.0, 1.0)
TRACK_HANDOVER_MIN_IOU = min(1.0, _env_float("KHOAI_TRACK_HANDOVER_MIN_IOU", 0.10, 0.0))
try:
    _entry_roi_raw = json.loads(os.getenv("KHOAI_RFID_ENTRY_ROI", ""))
    RFID_ENTRY_ROI = tuple((float(point[0]), float(point[1])) for point in _entry_roi_raw)
    if len(RFID_ENTRY_ROI) < 3 or any(not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0) for x, y in RFID_ENTRY_ROI):
        RFID_ENTRY_ROI = ()
except (TypeError, ValueError, json.JSONDecodeError):
    RFID_ENTRY_ROI = ()
RFID_ENTRY_ROI_FILE = Path(os.getenv("KHOAI_RFID_ENTRY_ROI_FILE", str(AI_DIR.parent / "data" / "rfid_entry_roi.json")))
EVIDENCE_INTERVAL_SECONDS = _env_float("KHOAI_EVIDENCE_INTERVAL_SECONDS", 1.0, 0.0)
TRACK_HOLD_SECONDS = _env_float("KHOAI_TRACK_HOLD_SECONDS", 5.0, 0.1)
# Preserve same-process Track/Decision state only across a short camera reconnect.
# Keep this <= the Decision Engine handover window; longer outages fail closed.
TRACK_STATE_PRESERVE_SECONDS = min(3.5, _env_float("KHOAI_TRACK_STATE_PRESERVE_SECONDS", 3.0, 0.0))
HANDOVER_MATCH_RADIUS = _env_float("KHOAI_HANDOVER_MATCH_RADIUS", 0.08, 0.0)
HANDOVER_MAX_GAP_SECONDS = _env_float("KHOAI_HANDOVER_MAX_GAP_SECONDS", 3.5, 0.0)
HANDOVER_EDGE_MARGIN_RATIO = min(0.20, _env_float("KHOAI_HANDOVER_EDGE_MARGIN_RATIO", 0.03, 0.0))
HANDOVER_EDGE_HISTORY_SECONDS = _env_float("KHOAI_HANDOVER_EDGE_HISTORY_SECONDS", 1.0, 0.1)
HANDOVER_EDGE_MIN_SAMPLES = _env_int("KHOAI_HANDOVER_EDGE_MIN_SAMPLES", 3, 2)
HANDOVER_EDGE_MIN_SPAN_SECONDS = _env_float("KHOAI_HANDOVER_EDGE_MIN_SPAN_SECONDS", 0.08, 0.0)
HANDOVER_EDGE_OUTWARD_SPEED_RATIO = _env_float("KHOAI_HANDOVER_EDGE_OUTWARD_SPEED_RATIO", 0.035, 0.0)
HANDOVER_EDGE_MIN_DISPLACEMENT_PX = _env_float("KHOAI_HANDOVER_EDGE_MIN_DISPLACEMENT_PX", 2.0, 0.0)
HANDOVER_EXCLUSION_RADIUS = _env_float("KHOAI_HANDOVER_EXCLUSION_RADIUS", 0.08, 0.0)
# Defensive Engine-side fallback; normal detector entry uses ENTER_CONFIRM_SECONDS above.
HANDOVER_RAW_INSIDE_CONFIRM_SECONDS = _env_float("KHOAI_HANDOVER_RAW_INSIDE_CONFIRM_SECONDS", 0.22, 0.0)
DECISION_EXIT_HYSTERESIS_SECONDS = _env_float("KHOAI_DECISION_EXIT_HYSTERESIS_SECONDS", 0.5, 0.0)
HEALTH_ESCALATION_SECONDS = _env_float("KHOAI_HEALTH_ESCALATION_SECONDS", 30.0, 0.0)
# Delay only health notifications for short camera-cadence instability. RFID remains fail-closed immediately.
CAMERA_UNSTABLE_DELAY_SECONDS = min(3.5, max(0.0, HEALTH_ESCALATION_SECONDS - 0.1)) if HEALTH_ESCALATION_SECONDS > 0 else 0.0
CAMERA_UNSTABLE_DELAY_SECONDS = _env_float("KHOAI_CAMERA_UNSTABLE_DELAY_SECONDS", CAMERA_UNSTABLE_DELAY_SECONDS, 0.0)
if HEALTH_ESCALATION_SECONDS > 0:
    CAMERA_UNSTABLE_DELAY_SECONDS = min(CAMERA_UNSTABLE_DELAY_SECONDS, max(0.0, HEALTH_ESCALATION_SECONDS - 0.1))
STARTUP_GRACE_SECONDS = _env_float("KHOAI_STARTUP_GRACE_SECONDS", 60.0, 0.0)
ENTRY_GRACE_SECONDS = _env_float("KHOAI_ENTRY_GRACE_SECONDS", 8.0, 0.0)
WRONG_ZONE_GRACE_SECONDS = _env_float("KHOAI_WRONG_ZONE_GRACE_SECONDS", 8.0, 0.0)
DWELL_REVIEW_SECONDS = _env_float("KHOAI_DWELL_REVIEW_SECONDS", 300.0, 0.0)
CAMERA_ZONE_ID = os.getenv("KHOAI_CAMERA_ZONE_ID", "external_usb_zone").strip() or "external_usb_zone"


def _normalize_rfid_uid(uid: str) -> str:
    """Canonicalize UID separators/case at the detector boundary."""
    normalized = re.sub(r"[\s:-]", "", str(uid)).upper()
    if not normalized:
        raise ValueError("RFID UID không được để trống.")
    return normalized
CAMERA_SCAN_MAX = _env_int("KHOAI_CAMERA_SCAN_MAX", 5, 0)

RED, GREEN, YELLOW = (0, 0, 255), (40, 220, 40), (0, 220, 255)


# --------------------------------------------------------------------------------------
# Vùng cấm: nạp / lưu / kiểm tra
# --------------------------------------------------------------------------------------
def _orientation(a: tuple[float, float], b: tuple[float, float],
                 c: tuple[float, float]) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _on_segment(a: tuple[float, float], b: tuple[float, float],
                p: tuple[float, float], eps: float = 1e-10) -> bool:
    return (min(a[0], b[0]) - eps <= p[0] <= max(a[0], b[0]) + eps and
            min(a[1], b[1]) - eps <= p[1] <= max(a[1], b[1]) + eps)


def _segments_intersect(a, b, c, d, eps: float = 1e-10) -> bool:
    o1, o2 = _orientation(a, b, c), _orientation(a, b, d)
    o3, o4 = _orientation(c, d, a), _orientation(c, d, b)
    if ((o1 > eps and o2 < -eps) or (o1 < -eps and o2 > eps)) and \
       ((o3 > eps and o4 < -eps) or (o3 < -eps and o4 > eps)):
        return True
    return ((abs(o1) <= eps and _on_segment(a, b, c, eps)) or
            (abs(o2) <= eps and _on_segment(a, b, d, eps)) or
            (abs(o3) <= eps and _on_segment(c, d, a, eps)) or
            (abs(o4) <= eps and _on_segment(c, d, b, eps)))


def validate_zone(zone: Sequence[tuple[float, float]]) -> None:
    if len(zone) < 3:
        raise ValueError("Vùng giám sát cần ít nhất 3 điểm.")
    if any(not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0) for x, y in zone):
        raise ValueError("Tọa độ vùng phải nằm trong khoảng 0–1.")
    if len(set(zone)) != len(zone):
        raise ValueError("Đa giác không được có các điểm trùng nhau.")
    area2 = sum(zone[i][0] * zone[(i + 1) % len(zone)][1] -
                zone[(i + 1) % len(zone)][0] * zone[i][1]
                for i in range(len(zone)))
    if abs(area2) / 2 < 0.002:
        raise ValueError("Vùng có diện tích bằng 0 hoặc quá nhỏ; hãy chọn lại các điểm.")
    count = len(zone)
    for i in range(count):
        a, b = zone[i], zone[(i + 1) % count]
        if a == b:
            raise ValueError("Đa giác không được có cạnh dài bằng 0.")
        for j in range(i + 1, count):
            # Adjacent edges share one endpoint by design; all other intersections
            # (including collinear overlaps and non-adjacent touching) are invalid.
            if j == i or j == (i + 1) % count or i == (j + 1) % count:
                continue
            c, d = zone[j], zone[(j + 1) % count]
            if _segments_intersect(a, b, c, d):
                raise ValueError("Đa giác ROI không được tự cắt hoặc chạm cạnh không liền kề.")


def load_zone_file(path: Path | None = None) -> tuple[tuple[tuple[float, float], ...], tuple[int, int] | None]:
    """Trả về (các điểm chuẩn hóa, frame_size lúc vẽ hoặc None)."""
    path = path or ZONE_FILE
    if not path.is_file():
        return DEFAULT_ZONE, None
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        points = data.get("points", data) if isinstance(data, dict) else data
        zone = tuple((float(p[0]), float(p[1])) for p in points)
        validate_zone(zone)
        size = None
        if isinstance(data, dict) and data.get("frame_size"):
            size = (int(data["frame_size"][0]), int(data["frame_size"][1]))
        return zone, size
    except (OSError, ValueError, TypeError, KeyError, IndexError, json.JSONDecodeError) as exc:
        logger.warning("Không đọc được file vùng %s (%s); dùng vùng mặc định", path, exc)
        return DEFAULT_ZONE, None


def save_zone_file(zone: Sequence[tuple[float, float]], frame_size: tuple[int, int] | None = None,
                   path: Path | None = None) -> Path:
    path = path or ZONE_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {"points": [[round(x, 6), round(y, 6)] for x, y in zone]}
    if frame_size:
        payload["frame_size"] = [int(frame_size[0]), int(frame_size[1])]
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp.replace(path)  # ghi nguyên tử: không để detector đọc phải file ghi dở
    return path


def zone_aspect_warning(zone_frame_size: tuple[int, int] | None,
                        camera_frame_size: tuple[int, int], tolerance: float = 0.03) -> str | None:
    """Cảnh báo khi tỷ lệ khung lúc vẽ ROI khác tỷ lệ khung camera hiện tại."""
    if not zone_frame_size:
        return None
    zone_width, zone_height = int(zone_frame_size[0]), int(zone_frame_size[1])
    camera_width, camera_height = int(camera_frame_size[0]), int(camera_frame_size[1])
    if min(zone_width, zone_height, camera_width, camera_height) <= 0:
        return None
    zone_ratio = zone_width / zone_height
    camera_ratio = camera_width / camera_height
    if abs(zone_ratio - camera_ratio) / camera_ratio <= max(0.0, float(tolerance)):
        return None
    return (f"Vùng được vẽ ở khung {zone_width}x{zone_height} nhưng camera đang là "
            f"{camera_width}x{camera_height} (khác tỉ lệ) -> vùng có thể lệch. Hãy vẽ lại vùng bảo vệ.")


def zone_to_pixels(zone: Sequence[tuple[float, float]], width: int, height: int) -> np.ndarray:
    """Chuẩn hóa -> pixel (float32). Cùng công thức (w-1, h-1) với draw_zone.py."""
    return np.asarray([(x * (width - 1), y * (height - 1)) for x, y in zone], dtype=np.float32)


def _inside(poly: np.ndarray, x: float, y: float) -> bool:
    return cv2.pointPolygonTest(poly, (float(x), float(y)), False) >= 0


def scale_zone(zone: Sequence[tuple[float, float]], factor: float) -> tuple[tuple[float, float], ...]:
    """Nới/thu đa giác quanh trọng tâm; tọa độ được giới hạn trong khung 0..1."""
    cx = sum(point[0] for point in zone) / len(zone)
    cy = sum(point[1] for point in zone) / len(zone)
    return tuple((min(1.0, max(0.0, cx + (x - cx) * factor)),
                  min(1.0, max(0.0, cy + (y - cy) * factor))) for x, y in zone)


def current_zone_period(now: datetime | None = None) -> str:
    """Chế độ ban ngày kết thúc lúc 18:00 theo BUSINESS_TZ."""
    local_now = now or datetime.now(BUSINESS_TZ)
    return "night" if local_now.hour >= 18 or local_now.hour < 6 else "day"


def is_box_in_zone(box: tuple[float, float, float, float], frame_size: tuple[int, int], poly: np.ndarray,
                   mode: str = "foot", zone_mask: np.ndarray | None = None,
                   overlap_min: float = 0.30, truncated_fallback: bool = True) -> bool:
    """Quyết định một bounding box người có nằm trong vùng không.

    foot    : điểm chạm sàn (giữa cạnh đáy box). Chính xác nhất cho vùng cấm vẽ trên mặt sàn.
              Nếu chân bị cắt ở đáy khung hình (người sát camera), dò thêm phần thân dưới.
    center  : tâm thân người.
    overlap : tỉ lệ diện tích box nằm trong vùng >= overlap_min (cần zone_mask).
    """
    x1, y1, x2, y2 = box
    width, height = frame_size
    box_h = max(1.0, y2 - y1)
    cx = (x1 + x2) / 2.0
    if mode == "center":
        return _inside(poly, cx, (y1 + y2) / 2.0)
    if mode == "overlap" and zone_mask is not None:
        ix1, iy1 = max(0, int(x1)), max(0, int(y1))
        ix2, iy2 = min(width, int(x2)), min(height, int(y2))
        if ix2 <= ix1 or iy2 <= iy1:
            return False
        roi = zone_mask[iy1:iy2, ix1:ix2]
        return float(np.count_nonzero(roi)) / float(roi.size) >= overlap_min
    foot_y = min(float(height - 1), y2)
    truncated = y2 >= height - 3
    if not truncated or not truncated_fallback:
        return _inside(poly, cx, foot_y)
    # Chân bị cắt: không biết chân thật ở đâu -> thử vài điểm dọc thân dưới của người.
    return any(_inside(poly, cx, y1 + box_h * t) for t in np.linspace(0.70, 1.0, 7))


# --------------------------------------------------------------------------------------
# CameraDetector
# --------------------------------------------------------------------------------------
class CameraDetector:
    """Chủ sở hữu duy nhất của camera. Dùng start() để chạy nền; stream/status chỉ đọc kết quả."""

    def __init__(self, camera_index: int | str | None = None,
                 zone: Sequence[tuple[float, float]] | None = None, *, model: Any | None = None) -> None:
        # ---- cấu hình camera ----
        raw_source = os.getenv("CAMERA_INDEX", AUTO) if camera_index is None else camera_index
        self._source_spec: int | str = parse_camera_source(raw_source)
        # ---- vùng ----
        loaded_zone, loaded_size = load_zone_file()
        self.zone: tuple[tuple[float, float], ...] = tuple((float(x), float(y)) for x, y in (zone or loaded_zone))
        validate_zone(self.zone)
        self._zone_frame_size: tuple[int, int] | None = None if zone else loaded_size
        self._zone_mtime = self._file_mtime()
        self._zone_check_at = 0.0
        self._zone_mask_cache: tuple[tuple[int, int, tuple], np.ndarray] | None = None
        # ---- đồng bộ & luồng ----
        self._lock = threading.RLock()                  # bảo vệ trạng thái nghiệp vụ
        self._life_lock = threading.Lock()              # start/stop
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []
        self._started_at = 0.0
        self._last_processed_at = float("-inf")
        self._last_detection_at = float("-inf")
        self._last_detections: list[dict[str, Any]] = []
        self._last_process_error: str | None = None
        self._health_failure_since: float | None = None
        self._health_condition_since: float | None = None
        self._health_reason: str | None = None
        self._health_alarm_owned = False
        self._health_event_active = False
        self._camera_alarm_owned = False
        self._raw_cond = threading.Condition()
        self._raw: np.ndarray | None = None
        self._raw_seq = 0
        self._last_raw_at = float("-inf")
        self._camera_frame_times: deque[float] = deque(maxlen=256)
        self._capture_last_tick = 0.0
        self._capture_fps = 0.0
        self._process_latency_ms = 0.0
        self._detection_count = 0
        self._out_cond = threading.Condition()
        self._out_jpeg: bytes | None = None
        self._out_seq = 0
        self._display_state: tuple[list[dict[str, Any]], np.ndarray, bool, set[int]] | None = None
        self._display_state_at = 0.0
        self._stream_fps = 0.0
        # ---- model ----
        self._model: Any | None = model
        self._model_error: str | None = None
        self._model_loading = False
        self._tracking_enabled = True
        # ---- trạng thái camera ----
        self._camera_info: OpenedCamera | None = None
        self._last_frame_size: tuple[int, int] | None = None
        self._camera_error: str | None = None
        self._camera_health: bool | None = None
        self._camera_offline_event_reported = False
        self._camera_offline_since: float | None = None
        self._track_state_preservation_last = "not_applicable"
        self._track_state_preservation_age: float | None = None
        self._fps = 0.0
        # ---- trạng thái theo dõi ----
        self._track_state: dict[int, dict[str, Any]] = {}
        self._inside_since: dict[int, float] = {}
        self._authorized_tracks: dict[int, dict[str, Any]] = {}
        self._decision_record_session_id = uuid.uuid4().hex
        self._decision_record_frame_seq = 0
        self._decision_record_session_started = False
        self._decision_engine = DecisionEngine(DecisionConfig(
            ENTRY_GRACE_SECONDS, WRONG_ZONE_GRACE_SECONDS, DWELL_REVIEW_SECONDS,
            track_hold_seconds=TRACK_HOLD_SECONDS,
            handover_max_gap_seconds=HANDOVER_MAX_GAP_SECONDS,
            handover_edge_margin_ratio=HANDOVER_EDGE_MARGIN_RATIO,
            handover_match_radius=HANDOVER_MATCH_RADIUS,
            handover_exclusion_radius=HANDOVER_EXCLUSION_RADIUS,
            handover_raw_inside_confirm_seconds=HANDOVER_RAW_INSIDE_CONFIRM_SECONDS,
            exit_hysteresis_seconds=DECISION_EXIT_HYSTERESIS_SECONDS,
            presence_release_seconds=_env_float("KHOAI_PRESENCE_RELEASE_SECONDS", 8.0, 0.0),
            anonymous_debounce_seconds=_env_float("KHOAI_ANONYMOUS_DEBOUNCE_SECONDS", 1.0, 0.0),
            health_escalation_seconds=HEALTH_ESCALATION_SECONDS,
            suspicious_seconds=_env_float("KHOAI_SUSPICIOUS_SECONDS", 30.0, 0.0),
            suspicious_gap_seconds=_env_float("KHOAI_SUSPICIOUS_GAP_SECONDS", 4.0, 0.0),
            suspicious_approach_min_seconds=_env_float("KHOAI_SUSPICIOUS_APPROACH_MIN_SECONDS", 2.0, 0.0),
            suspicious_approach_count=_env_int("KHOAI_SUSPICIOUS_APPROACH_COUNT", 3, 1),
            suspicious_approach_window_seconds=_env_float("KHOAI_SUSPICIOUS_APPROACH_WINDOW_SECONDS", 120.0, 0.0)))
        self._decision_tracks: dict[str, dict[str, Any]] = {}
        self._spatial_tracks: dict[str, dict[str, Any]] = {}
        self._homography = HomographyCalibrationManager(
            os.getenv("KHOAI_HOMOGRAPHY_FILE", str(AI_DIR / "homography.json")),
            os.getenv("KHOAI_CAMERA_ID", "usb_external"))
        self._dwell_alerted: set[int] = set()
        self._events: deque[dict[str, Any]] = deque(maxlen=MAX_EVENTS)
        self._evidence_last_saved_at = float("-inf")
        self._last_evidence_url: str | None = None
        self._last_evidence_at = float("-inf")
        self._last_evidence_timestamp = ""
        self._rfid_tickets: dict[str, dict[str, Any]] = {}
        # Heatmap mật độ vị trí người, lưới thấp để nhẹ CPU/RAM; suy giảm theo thời gian.
        self._heatmap = np.zeros((HEATMAP_HEIGHT, HEATMAP_WIDTH), dtype=np.float32)
        self._heatmap_last_tick = time.monotonic()
        self.person_in_zone = False
        self.warning_person_ids: list[int] = []
        self.review_person_ids: list[int] = []
        self.alarm_person_ids: list[int] = []
        self.anti_theft_enabled = True  # giữ hành vi giám sát hiện tại khi nâng cấp
        self.alarm_state = "SAFE"
        self.zone_period = current_zone_period()
        self.tracked_person_ids: list[int] = []
        self.last_event: dict[str, Any] | None = None
        self.last_frame_at: str | None = None
        self._zone_warning: str | None = None
        self.rfid_entry_roi = tuple(RFID_ENTRY_ROI)
        try:
            if RFID_ENTRY_ROI_FILE.is_file():
                stored = json.loads(RFID_ENTRY_ROI_FILE.read_text(encoding="utf-8"))
                points = tuple((float(point[0]), float(point[1])) for point in stored.get("points", []))
                if len(points) >= 3 and all(0.0 <= x <= 1.0 and 0.0 <= y <= 1.0 for x, y in points):
                    self.rfid_entry_roi = points
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            logger.exception("Không đọc được ROI cửa RFID đã lưu")

    # ---------------------------------------------------------------- vòng đời
    def start(self) -> None:
        """Bắt đầu đọc camera + chạy AI ở nền. Gọi nhiều lần vẫn an toàn."""
        with self._life_lock:
            if any(t.is_alive() for t in self._threads):
                return
            self._stop.clear()
            self._started_at = time.monotonic()
            self._last_processed_at = float("-inf")
            self._last_process_error = None
            self._health_failure_since = None
            self._health_condition_since = None
            self._health_reason = None
            self._health_alarm_owned = False
            self._health_event_active = False
            self._camera_offline_event_reported = False
            self._camera_frame_times.clear()
            self._threads = [
                threading.Thread(target=self._capture_loop, name="khoai-capture", daemon=True),
                threading.Thread(target=self._process_loop, name="khoai-ai", daemon=True),
                threading.Thread(target=self._render_loop, name="khoai-render", daemon=True),
                threading.Thread(target=self._health_watchdog_loop, name="khoai-health", daemon=True),
            ]
            for thread in self._threads:
                thread.start()
            logger.info("KhoAI camera worker started (source=%s)", self._source_spec)

    def stop(self) -> None:
        with self._life_lock:
            self._stop.set()
            with self._raw_cond:
                self._raw_cond.notify_all()
            with self._out_cond:
                self._out_cond.notify_all()
            for thread in self._threads:
                if thread is not threading.current_thread():
                    thread.join(timeout=5)
            self._threads = []
        with self._lock:
            self._camera_info = None
            self.person_in_zone = False
            self.tracked_person_ids = []
            self._display_state = None
            self._display_state_at = 0.0
            self._reset_tracking()
            self._authorized_tracks.clear()
            self._rfid_tickets.clear()
            self._decision_engine.reset()
            self._decision_tracks.clear()
            self.alarm_state = "SAFE"
            self.alarm_person_ids = []
            self.warning_person_ids = []
            self.review_person_ids = []
            self._track_state_preservation_last = "reset_on_stop"
            self._track_state_preservation_age = None
        with self._raw_cond:
            self._raw = None
            self._last_raw_at = float("-inf")
        with self._lock:
            self._camera_frame_times.clear()

    close = stop  # tương thích tên cũ

    @property
    def running(self) -> bool:
        return any(t.is_alive() for t in self._threads)

    def set_camera_source(self, source: int | str | None) -> None:
        """Đổi camera khi đang chạy (index, 'auto', URL...)."""
        was_running = self.running
        self.stop()
        self._source_spec = parse_camera_source(source)
        with self._lock:
            self._camera_error = None
        if was_running:
            self.start()

    # ---------------------------------------------------------------- vùng cấm
    @staticmethod
    def _file_mtime() -> int | None:
        try:
            # Nanosecond precision avoids missing rapid atomic replacements on filesystems
            # whose floating-point mtime representation is too coarse.
            return ZONE_FILE.stat().st_mtime_ns
        except OSError:
            return None

    def _reset_tracking(self) -> None:
        self._track_state.clear()
        self._inside_since.clear()
        self._dwell_alerted.clear()

    def set_zone(self, points: Sequence[tuple[float, float]], save: bool = True,
                 frame_size: tuple[int, int] | None = None) -> None:
        zone = tuple((float(x), float(y)) for x, y in points)
        validate_zone(zone)
        with self._lock:
            self.zone = zone
            if frame_size:
                self._zone_frame_size = (int(frame_size[0]), int(frame_size[1]))
            elif self._camera_info is not None:
                self._zone_frame_size = (self._camera_info.width, self._camera_info.height)
            self._reset_tracking()
            if save:
                save_zone_file(zone, self._zone_frame_size)
                self._zone_mtime = self._file_mtime()

    def _maybe_reload_zone(self, now: float) -> None:
        """Nạp lại zone.json nếu bạn vừa vẽ lại bằng draw_zone.py (không cần restart server)."""
        if now - self._zone_check_at < 1.0:
            return
        self._zone_check_at = now
        mtime = self._file_mtime()
        if mtime is None or mtime == self._zone_mtime:
            return
        zone, size = load_zone_file()
        with self._lock:
            self._zone_mtime = mtime
            geometry_changed = zone != self.zone
            metadata_changed = size != self._zone_frame_size
            if geometry_changed:
                self.zone = zone
                self._reset_tracking()
                logger.info("Đã nạp lại vùng cấm từ %s", ZONE_FILE)
            # Frame dimensions are meaningful independently of normalized polygon points.
            # A user may redraw/save the same ROI at a different camera resolution.
            if geometry_changed or metadata_changed:
                self._zone_frame_size = size

    def _zone_mask(self, width: int, height: int, zone: tuple, poly_i: np.ndarray) -> np.ndarray:
        key = (width, height, zone)
        if self._zone_mask_cache is None or self._zone_mask_cache[0] != key:
            mask = np.zeros((height, width), dtype=np.uint8)
            cv2.fillPoly(mask, [poly_i.reshape(-1, 1, 2)], 255)
            self._zone_mask_cache = (key, mask)
        return self._zone_mask_cache[1]

    # ---------------------------------------------------------------- liên kết thẻ & sự kiện
    def create_rfid_ticket(self, uid: str, name: str | None = None,
                           allowed_zones: Sequence[str] = (), ttl_seconds: float = 20.0) -> dict[str, Any]:
        """Create a one-use ticket. Automatic binding is opt-in and fail-closed.

        The default is manual association because camera/reader geometry has not been
        verified. When explicitly enabled, only a single Track already visible in the
        configured entry ROI at swipe time can be considered, and any candidate-set
        change during the stability window permanently requires manual association.
        """
        uid = _normalize_rfid_uid(uid)
        now = time.monotonic()
        ttl = min(20.0, max(1.0, float(ttl_seconds)))
        with self._lock:
            self._prune_rfid_tickets_locked(now)
            if not self._camera_stream_stable_locked(now):
                raise RuntimeError("Camera USB chưa có luồng frame ổn định; không thể tạo ticket RFID.")
            if uid not in self._rfid_tickets and len(self._rfid_tickets) >= MAX_PENDING_RFID_TICKETS:
                return {"uid": uid, "expires_in": 0.0, "pending_binding": False,
                        "manual_confirmation_required": True, "capacity_reached": True}
            candidate_ids: list[int] = []
            if (RFID_AUTO_BIND_ENABLED and self.rfid_entry_roi and self._last_frame_size
                    and now - self._last_raw_at <= CAMERA_FRAME_STALE_SECONDS
                    and now - self._last_detection_at <= RFID_BIND_MAX_OBSERVATION_GAP_SECONDS):
                width, height = self._last_frame_size
                roi = np.array([[(int(x * width), int(y * height)) for x, y in self.rfid_entry_roi]], dtype=np.int32)
                roi_detections = []
                for detection in self._last_detections:
                    x1, y1, x2, y2 = map(float, detection["box"])
                    center = (int((x1 + x2) / 2), int((y1 + y2) / 2))
                    if cv2.pointPolygonTest(roi[0], center, False) >= 0:
                        roi_detections.append(detection)
                if len(roi_detections) == 1 and roi_detections[0].get("id") is not None:
                    candidate_ids = [int(roi_detections[0]["id"])]
            auto_candidate = candidate_ids[0] if len(candidate_ids) == 1 else None
            self._rfid_tickets[uid] = {"uid": uid, "name": name, "created_at": now,
                "expires_at": now + ttl,
                "allowed_zones": sorted({str(z) for z in allowed_zones}),
                "bind_candidate_track_id": auto_candidate,
                "bind_candidate_since": now if auto_candidate is not None else None,
                "bind_last_observed_at": self._last_detection_at if auto_candidate is not None else None,
                "bind_observation_count": 1 if auto_candidate is not None else 0,
                "bind_snapshot_track_ids": sorted(candidate_ids),
                "auto_bind_blocked": not (RFID_AUTO_BIND_ENABLED and len(candidate_ids) == 1)}
            return {"uid": uid, "expires_in": ttl, "pending_binding": True,
                    "auto_binding_enabled": bool(RFID_AUTO_BIND_ENABLED),
                    "manual_confirmation_required": not (RFID_AUTO_BIND_ENABLED and len(candidate_ids) == 1)}

    def pending_rfid_tickets(self) -> list[dict[str, Any]]:
        now = time.monotonic()
        with self._lock:
            self._prune_rfid_tickets_locked(now)
            return [{"uid": uid, "name": ticket.get("name"),
                     "expires_in": round(max(0.0, float(ticket["expires_at"]) - now), 1),
                     "allowed_zones": list(ticket.get("allowed_zones", [])),
                     "auto_binding_enabled": bool(RFID_AUTO_BIND_ENABLED),
                     "manual_confirmation_required": bool(ticket.get("auto_bind_blocked", True))}
                    for uid, ticket in self._rfid_tickets.items()]

    def _prune_rfid_tickets_locked(self, now: float) -> None:
        """Remove expired tickets; caller holds ``self._lock``."""
        for uid in list(self._rfid_tickets):
            try:
                expires_at = float(self._rfid_tickets[uid].get("expires_at", 0.0))
            except (TypeError, ValueError, OverflowError):
                expires_at = 0.0
            if now >= expires_at:
                self._rfid_tickets.pop(uid, None)

    def set_rfid_entry_roi(self, points: Sequence[Sequence[float]]) -> tuple[tuple[float, float], ...]:
        normalized = tuple((float(point[0]), float(point[1])) for point in points)
        if len(normalized) < 3 or len(normalized) > 30:
            raise ValueError("ROI cửa cần từ 3 đến 30 điểm.")
        if any(not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0) for x, y in normalized):
            raise ValueError("Tọa độ ROI cửa phải nằm trong khoảng 0–1.")
        validate_zone(normalized)
        payload = {"points": [[x, y] for x, y in normalized]}
        RFID_ENTRY_ROI_FILE.parent.mkdir(parents=True, exist_ok=True)
        temporary = RFID_ENTRY_ROI_FILE.with_suffix(RFID_ENTRY_ROI_FILE.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(RFID_ENTRY_ROI_FILE)
        with self._lock:
            self.rfid_entry_roi = normalized
        return normalized

    def track_thumbnail_jpeg(self, track_id: int) -> bytes | None:
        with self._raw_cond:
            frame = self._raw.copy() if self._raw is not None else None
        with self._lock:
            state = self._track_state.get(int(track_id))
            if frame is None or not state or time.monotonic() - float(state.get("last_seen_at", 0.0)) > 3.0:
                return None
            box = state.get("last_box")
        if not box:
            return None
        height, width = frame.shape[:2]
        x1, y1, x2, y2 = map(int, box)
        pad_x = max(12, int((x2 - x1) * 0.15))
        pad_y = max(12, int((y2 - y1) * 0.10))
        x1, y1 = max(0, x1 - pad_x), max(0, y1 - pad_y)
        x2, y2 = min(width, x2 + pad_x), min(height, y2 + pad_y)
        crop = frame[y1:y2, x1:x2]
        if crop.size == 0:
            return None
        ok, encoded = cv2.imencode(".jpg", crop, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
        return encoded.tobytes() if ok else None

    def has_rfid_ticket(self, uid: str) -> bool:
        try:
            uid = _normalize_rfid_uid(uid)
        except ValueError:
            return False
        with self._lock:
            self._prune_rfid_tickets_locked(time.monotonic())
            ticket = self._rfid_tickets.get(uid)
            return bool(ticket and time.monotonic() < float(ticket["expires_at"]))

    def associate_card(self, track_id: int, uid: str, name: str | None = None,
                       allowed_zones: Sequence[str] = ()) -> dict[str, Any]:
        """Atomically consume a live RFID ticket and bind it to a currently visible Track."""
        track_id = int(track_id)
        uid = _normalize_rfid_uid(uid)
        with self._lock:
            now = time.monotonic()
            ticket = self._rfid_tickets.get(uid)
            if ticket is None or now >= float(ticket.get("expires_at", 0.0)):
                self._rfid_tickets.pop(uid, None)
                raise ValueError("RFID ticket không tồn tại hoặc đã hết hạn; hãy quẹt thẻ lại.")
            if not self._camera_stream_stable_locked(now):
                raise ValueError("Camera chưa có luồng frame ổn định; không thể gắn quyền RFID.")
            state = self._track_state.get(track_id)
            if not state or now - float(state.get("last_seen_at", float("-inf"))) > 1.5:
                raise ValueError("Track không còn hiển thị; không thể gắn quyền RFID.")
            zones = ticket.get("allowed_zones") or allowed_zones
            if not zones:
                raise ValueError("Thẻ không có quyền vùng; từ chối gắn quyền.")
            name = ticket.get("name") or name
            self._rfid_tickets.pop(uid, None)
            self._authorized_tracks[track_id] = {"uid": uid, "name": name, "at": now,
                "allowed_zones": sorted({str(z) for z in zones})}
            self._dwell_alerted.discard(track_id)
            return {"track_id": track_id, "uid": uid, "name": name, "associated": True,
                    "ticket_consumed": True}

    def revoke_track(self, track_id: int) -> None:
        with self._lock:
            self._authorized_tracks.pop(int(track_id), None)

    def revoke_uid(self, uid: str) -> dict[str, Any]:
        uid = _normalize_rfid_uid(uid)
        with self._lock:
            removed = [tid for tid, auth in self._authorized_tracks.items()
                       if re.sub(r"[\s:-]", "", str(auth.get("uid", ""))).upper() == uid]
            for tid in removed:
                self._authorized_tracks.pop(tid, None)
                self._emit("authorization_revoked", tid,
                    f"Quyền RFID của Track {tid} đã bị thu hồi do thẻ {uid} bị khóa hoặc xóa.",
                    severity="warning", authorized=False, card_uid=uid, reason="card_revoked")
            self._rfid_tickets.pop(uid, None)
            return {"uid": uid, "revoked_track_ids": sorted(removed), "revoked": len(removed)}

    def _build_decision_observations(self, now: float,
                                    detections: Sequence[dict[str, Any]] | None = None,
                                    *, immediate_alarm: bool = False) -> list[dict[str, Any]]:
        """Build the canonical observation shape for both live frames and re-arming."""
        observations: list[dict[str, Any]] = []
        if detections is None:
            for tid, state in self._track_state.items():
                auth = self._authorized_tracks.get(tid, {})
                observations.append({"track_id": tid, "zone_id": CAMERA_ZONE_ID,
                    "inside": bool(state.get("inside")), "warning": tid in self.warning_person_ids,
                    "authorized_zones": auth.get("allowed_zones", []),
                    "immediate_alarm": bool(immediate_alarm and state.get("inside")),
                    "dwell_seconds": max(0.0, now - self._inside_since.get(tid, now))
                        if state.get("inside") else 0.0})
            return observations
        for det in detections:
            tid = det.get("id")
            if tid is None:
                continue
            auth = self._authorized_tracks.get(int(tid), {})
            inside = bool(det.get("inside"))
            started = self._inside_since.get(int(tid), now)
            observations.append({"track_id": int(tid), "zone_id": CAMERA_ZONE_ID,
                # Preserve instantaneous geometry separately from hysteresis-confirmed
                # occupancy. A replacement Track can arrive on the first inside frame
                # with inside=False but raw_inside=True; dropping this bit resets the
                # intrusion session during an otherwise valid ID handover.
                "inside": inside, "raw_inside": bool(det.get("raw_inside")),
                "warning": bool(det.get("raw_warning") and not inside),
                "position": det.get("normalized_footpoint"),
                "bbox": [float(value) for value in det.get("box", ())],
                "footpoint": list(det.get("normalized_footpoint") or ()),
                "card_authorized": bool(auth),
                "exited_frame_edge": bool(det.get("exited_frame_edge", False)),
                "exit_boundary_inside": bool(det.get("exit_boundary_inside", inside)),
                "authorized_zones": auth.get("allowed_zones", []),
                "immediate_alarm": False,
                "dwell_seconds": max(0.0, now - started) if inside else 0.0})
        return observations

    def _evaluate_decision_engine(self, observations: Sequence[dict[str, Any]], now: float,
                                  anonymous_inside: bool = False,
                                  frame_size: tuple[int, int] | None = None):
        """Single adapter for all Decision Engine evaluations, including health inputs."""
        health_elapsed = (max(0.0, now - self._health_failure_since)
                          if self._health_failure_since is not None else 0.0)
        health_fault = bool(self.anti_theft_enabled and self._health_failure_since is not None
                            and (self._health_reason != "camera_unstable"
                                 or health_elapsed >= CAMERA_UNSTABLE_DELAY_SECONDS))
        decision = self._decision_engine.evaluate(observations, armed=self.anti_theft_enabled,
            now=now, anonymous_inside=anonymous_inside, health_fault=health_fault,
            health_fault_elapsed=health_elapsed)
        # Record/replay is opt-in, stores coordinates and engine inputs only, and
        # is deliberately independent of persistence/incident database code.
        if os.getenv("KHOAI_DECISION_RECORD_ENABLED", "0").strip().lower() in {"1", "true", "yes", "on"}:
            try:
                from .decision_replay import append_frame_record
                self._decision_record_frame_seq += 1
                append_frame_record(os.getenv("KHOAI_DECISION_RECORD_PATH",
                    str(AI_DIR.parent / "data" / "decision_replay.jsonl")),
                    config=self._decision_engine.config, observations=list(observations),
                    armed=self.anti_theft_enabled, now=now, anonymous_inside=anonymous_inside,
                    health_fault=health_fault, health_fault_elapsed=health_elapsed,
                    events=list(decision.events), alarm_state=decision.alarm_state,
                    session_id=self._decision_record_session_id,
                    frame_seq=self._decision_record_frame_seq, frame_size=frame_size,
                    session_start=not self._decision_record_session_started)
                self._decision_record_session_started = True
            except Exception:
                logger.exception("Không ghi được Decision Engine replay record")
        self.alarm_state = decision.alarm_state
        self._decision_tracks = dict(decision.tracks)
        return decision

    def set_anti_theft(self, enabled: bool) -> dict[str, Any]:
        """Bật/tắt chống trộm và đánh giá occupancy hiện tại qua cùng Decision Engine."""
        with self._lock:
            previous = self.anti_theft_enabled
            self.anti_theft_enabled = bool(enabled)
            now = time.monotonic()
            camera_ok = self._camera_stream_stable_locked(now)
            ai_ok = self._model is not None and now - self._last_processed_at < 3.0
            startup_grace = self._started_at > 0 and now - self._started_at < STARTUP_GRACE_SECONDS
            if self.anti_theft_enabled and (not camera_ok or not ai_ok) and not startup_grace:
                reason = ("camera_offline" if now - self._last_raw_at >= CAMERA_FRAME_STALE_SECONDS else "camera_unstable") if not camera_ok else "ai_model_unavailable" if self._model is None else "ai_processing_stalled"
                if self._health_reason != reason or self._health_failure_since is None:
                    self._health_reason = reason
                    onset = (self._camera_instability_since_locked(now) if reason == "camera_unstable"
                             else (self._last_raw_at + CAMERA_RECOVERY_MAX_FRAME_GAP_SECONDS
                                   if reason == "camera_offline" and self._last_raw_at > 0 else now))
                    self._health_failure_since = onset
                    if self._health_condition_since is None:
                        self._health_condition_since = onset
            elif not self.anti_theft_enabled or startup_grace:
                self._health_failure_since = None
            observations = self._build_decision_observations(now, immediate_alarm=bool(enabled))
            health_elapsed = (max(0.0, now - self._health_failure_since)
                              if self._health_failure_since is not None else 0.0)
            health_fault = bool(self.anti_theft_enabled and self._health_failure_since is not None
                                and (self._health_reason != "camera_unstable"
                                     or health_elapsed >= CAMERA_UNSTABLE_DELAY_SECONDS))
            old_state = self.alarm_state
            decision = self._evaluate_decision_engine(observations, now)
            for item in decision.events:
                if item.get("type") == "alarm_state_changed":
                    self._emit("alarm_state_changed", -1, f"Trạng thái an ninh: {item.get('state')}.",
                               severity=item.get("severity", "info"), alarm_state=item.get("state"),
                               reason="health_fault" if health_fault else None,
                               health_reason=self._health_reason if health_fault else None)
            next_state = self.alarm_state
            if previous != self.anti_theft_enabled:
                self._emit("anti_theft_enabled" if enabled else "anti_theft_disabled", -1,
                           "Đã bật hệ thống chống trộm." if enabled else "Đã tắt hệ thống chống trộm.",
                           severity="high" if next_state == "ALARM" else "info", alarm_state=next_state)
            alarm_ids = sorted(int(item["track_id"]) for item in decision.tracks.values()
                               if item.get("state") == "ALARM" and item.get("track_id") is not None)
            warning_ids = sorted(int(item["track_id"]) for item in decision.tracks.values()
                                 if item.get("state") == "WARNING" and item.get("track_id") is not None)
            self.alarm_person_ids = alarm_ids
            self.warning_person_ids = warning_ids
            self.review_person_ids = sorted(int(item["track_id"]) for item in decision.tracks.values()
                                 if item.get("state") == "REVIEW" and item.get("track_id") is not None)
            if enabled and old_state != "ALARM" and next_state == "ALARM":
                for tid in alarm_ids:
                    self._emit("armed_occupied_zone", tid,
                               f"Bật chống trộm: phát hiện người ID {tid} đã ở trong vùng ALARM.",
                               severity="critical", authorized=tid in self._authorized_tracks)
            return {"anti_theft_enabled": self.anti_theft_enabled, "alarm_state": self.alarm_state,
                    "alarm_person_ids": alarm_ids, "warning_person_ids": warning_ids,
                    "review_person_ids": list(self.review_person_ids)}

    def get_events(self, limit: int = 30) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(event) for event in list(self._events)[:max(1, min(limit, MAX_EVENTS))]]

    def _set_camera_health(self, available: bool, error: str | None = None) -> None:
        """Ghi nhận một lần chuyển trạng thái camera, tránh lặp sự kiện khi đang mất tín hiệu."""
        with self._lock:
            previous = self._camera_health
            self._camera_health = bool(available)
            self._camera_error = None if available else error
            if previous is available:
                return
            if available:
                if previous is False:
                    now = time.monotonic()
                    outage_start = self._camera_offline_since
                    outage_age = max(0.0, now - outage_start) if outage_start is not None else float("inf")
                    self._track_state_preservation_age = round(outage_age, 3)
                    # A camera gap breaks visual identity continuity. Preserve only the
                    # decision/session context for short outages; never preserve RFID credentials.
                    self._authorized_tracks.clear()
                    self._rfid_tickets.clear()
                    if outage_age <= TRACK_STATE_PRESERVE_SECONDS:
                        # Keep the old decision session for the existing one-to-one,
                        # spatial-temporal handover checks. Do not manufacture a match.
                        self._track_state_preservation_last = "preserved_short_reconnect"
                    else:
                        self._reset_tracking()
                        self._authorized_tracks.clear()
                        self._decision_engine.reset()
                        self._decision_tracks.clear()
                        self.alarm_person_ids = []
                        self.warning_person_ids = []
                        self.review_person_ids = []
                        self._track_state_preservation_last = "reset_after_long_outage"
                    self._camera_offline_since = None
                    if self._camera_offline_event_reported:
                        self._emit("camera_recovered", -1, "Camera USB bên ngoài đã kết nối lại.",
                                   severity="info", camera_role="external_usb",
                                   track_state_policy=self._track_state_preservation_last,
                                   outage_seconds=self._track_state_preservation_age)
                        self._health_event_active = False
                        self._health_failure_since = None
                        self._health_condition_since = None
                        self._health_reason = None
                    self._camera_offline_event_reported = False
            else:
                now = time.monotonic()
                # Measure from the last successfully published frame, not from the
                # delayed health transition after the capture retry threshold.
                self._camera_offline_since = (self._last_raw_at if self._last_raw_at > 0 else now)
                self._camera_frame_times.clear()
                self._authorized_tracks.clear()
                self._rfid_tickets.clear()
                startup_grace = self._started_at > 0 and now - self._started_at < STARTUP_GRACE_SECONDS
                if not startup_grace:
                    onset = self._camera_offline_since + CAMERA_RECOVERY_MAX_FRAME_GAP_SECONDS
                    if self._health_condition_since is None:
                        self._health_condition_since = onset
                    if self._health_failure_since is None and self.anti_theft_enabled:
                        self._health_failure_since = onset
                    self._health_reason = "camera_offline"
                if not startup_grace and not self._camera_offline_event_reported:
                    self._emit("camera_offline", -1, error or "Camera USB bên ngoài mất kết nối.",
                               severity="critical", camera_role="external_usb")
                    self._camera_offline_event_reported = True
                    self._health_event_active = True

    def _emit(self, event_type: str, track_id: int, message: str, **extra: Any) -> None:
        event_id = uuid.uuid4().hex
        event = {"event_id": event_id,
                 "event_at": datetime.now(BUSINESS_TZ).isoformat(timespec="seconds"),
                 "type": event_type, "track_id": track_id, "message": message,
                 "evidence_filename": f"{event_id}.jpg", "evidence_url": None,
                 "evidence_expired": False, "evidence_status": "pending", **extra}
        self._events.appendleft(event)
        self.last_event = event
        logger.warning("KhoAI event: %s", event)

    def _attach_evidence(self, jpeg: bytes | None, event_ids_before: set[str]) -> None:
        """Attach one image URL to every event from a frame; reuse last image during cooldown."""
        with self._lock:
            frame_events = [event for event in self._events
                            if event.get("event_id") not in event_ids_before]
            if not frame_events:
                return
            if not jpeg:
                for event in frame_events:
                    if event.get("evidence_status") == "pending":
                        event["evidence_status"] = "failed"
                        event["evidence_failure_reason"] = "frame_unavailable"
                return
            now = time.monotonic()
            critical = any(str(event.get("severity", "")).lower() in {"critical", "high", "severe"}
                           or event.get("type") in {"unauthorized_entry", "wrong_zone", "anonymous_zone_alarm"}
                           for event in frame_events)
            should_save = critical or now - self._evidence_last_saved_at >= EVIDENCE_INTERVAL_SECONDS
            if not should_save and self._last_evidence_url:
                age_ms = max(0.0, now - self._last_evidence_at) * 1000.0
                for event in frame_events:
                    event["evidence_url"] = self._last_evidence_url
                    event["evidence_filename"] = self._last_evidence_url.rsplit("/", 1)[-1]
                    event["evidence_status"] = "available"
                    event["evidence_reused"] = True
                    event["image_age_ms"] = round(age_ms, 1)
                    event["evidence_timestamp"] = self._last_evidence_timestamp
                return
            evidence_id = uuid.uuid4().hex
            evidence_url = f"/api/camera/evidence/{evidence_id}.jpg"
            evidence_timestamp = datetime.now(BUSINESS_TZ).isoformat(timespec="milliseconds")
        try:
            EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
            with self._lock:
                destination = EVIDENCE_DIR / str(frame_events[0].get("evidence_filename") or f"{evidence_id}.jpg")
            temporary = destination.with_suffix(".jpg.tmp")
            temporary.write_bytes(jpeg)
            temporary.replace(destination)
            with self._lock:
                shared_url = f"/api/camera/evidence/{destination.name}"
                for event in frame_events:
                    event["evidence_filename"] = destination.name
                    event["evidence_url"] = shared_url
                    event["evidence_status"] = "available"
                    event["evidence_reused"] = False
                    event["image_age_ms"] = 0
                    event["evidence_timestamp"] = evidence_timestamp
                self._evidence_last_saved_at = time.monotonic()
                self._last_evidence_url = f"/api/camera/evidence/{destination.name}"
                self._last_evidence_at = self._evidence_last_saved_at
                self._last_evidence_timestamp = evidence_timestamp
        except OSError:
            with self._lock:
                for event in frame_events:
                    event["evidence_url"] = None
                    event["evidence_status"] = "failed"
                    event["evidence_failure_reason"] = "write_failed"
            logger.warning("Không lưu được ảnh bằng chứng cho frame %s", evidence_id, exc_info=True)

    def heatmap_jpeg(self) -> bytes | None:
        """Tạo ảnh nhiệt mật độ xuất hiện người trên khung camera hiện tại."""
        with self._raw_cond:
            frame = self._raw.copy() if self._raw is not None else None
        if frame is None:
            return None
        with self._lock:
            grid = self._heatmap.copy()
            zone = self.zone
        height, width = frame.shape[:2]
        resized = cv2.resize(grid, (width, height), interpolation=cv2.INTER_CUBIC)
        resized = cv2.GaussianBlur(resized, (0, 0), sigmaX=max(3, width / 100))
        max_value = float(resized.max())
        if max_value > 1e-6:
            normalized = np.clip(resized / max_value * 255.0, 0, 255).astype(np.uint8)
            colors = cv2.applyColorMap(normalized, cv2.COLORMAP_JET)
            active = (normalized > 8).astype(np.float32)[..., None]
            frame = np.clip(frame.astype(np.float32) * (1.0 - 0.38 * active) + colors.astype(np.float32) * (0.38 * active), 0, 255).astype(np.uint8)
        poly = zone_to_pixels(zone, width, height).round().astype(np.int32)
        cv2.polylines(frame, [poly.reshape(-1, 1, 2)], True, YELLOW, 2)
        cv2.putText(frame, "HEATMAP - MAT DO XUAT HIEN NGUOI", (10, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.55, YELLOW, 2, cv2.LINE_AA)
        ok, encoded = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 82])
        return encoded.tobytes() if ok else None

    def status(self) -> dict[str, Any]:
        with self._lock:
            info = self._camera_info
            now_mono = time.monotonic()
            available = self._camera_stream_stable_locked(now_mono)
            startup_grace = self._started_at > 0 and now_mono - self._started_at < STARTUP_GRACE_SECONDS
            model_ok = self._model is not None
            processed_fresh = (now_mono - self._last_processed_at) < 3.0
            ai_ok = model_ok and processed_fresh
            return {
                "running": self.running,
                "camera_available": available,
                "camera_ok": available,
                "ai_ok": ai_ok,
                "startup_grace": startup_grace,
                "processed_frame_age_ms": round(max(0.0, now_mono - self._last_processed_at) * 1000, 1)
                    if self._last_processed_at > 0 else None,
                "ai_error": self._last_process_error or self._model_error,
                "camera_health": "online" if available else "offline",
                "camera_unstable_delay_seconds": CAMERA_UNSTABLE_DELAY_SECONDS,
                "health_failure_age_seconds": round(max(0.0, now_mono - self._health_failure_since), 1)
                    if self._health_failure_since is not None else None,
                "camera_role": "external_usb",
                "camera_source": info.describe() if info else str(self._source_spec),
                "camera_error": None if available else self._camera_error,
                "frame_size": list(self._last_frame_size) if self._last_frame_size else ([info.width, info.height] if info else None),
                "fps": round(self._fps, 1),  # tương thích dashboard cũ: FPS AI
                "process_fps": round(self._fps, 1),
                "capture_fps": round(self._capture_fps, 1),
                "stream_fps": round(self._stream_fps, 1),
                "overlay_age_ms": round(max(0.0, time.monotonic() - self._display_state_at) * 1000, 1)
                    if self._display_state_at > 0 else None,
                "process_latency_ms": round(self._process_latency_ms, 1),
                "frame_age_ms": round(max(0.0, time.monotonic() - self._last_raw_at) * 1000, 1)
                    if self._last_raw_at > 0 else None,
                "detections": self._detection_count,
                "people_in_zone": sum(1 for item in self._track_state.values() if bool(item.get("inside"))),
                "zone_points": [[x, y] for x, y in self.zone],
                "zone_frame_size": list(self._zone_frame_size) if self._zone_frame_size else None,
                "model_loaded": self._model is not None,
                "model_loading": self._model_loading,
                "model_error": self._model_error,
                "tracking": self._tracking_enabled,
                "tracking_enabled": bool(self._tracking_enabled),
                "zone_mode": ZONE_MODE,
                "zone_warning": self._zone_warning,
                "person_in_zone": self.person_in_zone,
                "anti_theft_enabled": self.anti_theft_enabled,
                "alarm_state": self.alarm_state,
                "alarm": "severe" if self.alarm_state == "ALARM" else "warning" if self.alarm_state in {"WARNING", "PENDING"} else "off",
                "latched": False,
                "acknowledged": False,
                "siren": self.alarm_state == "ALARM",
                "incidents": [],
                "health_failure_reason": self._health_reason,
                "track_state_preservation": {"enabled": True, "window_seconds": TRACK_STATE_PRESERVE_SECONDS,
                    "last_action": self._track_state_preservation_last,
                    "last_outage_seconds": self._track_state_preservation_age,
                    "scope": "same_process_camera_reconnect_only"},
                "health_failure_age_seconds": round(max(0.0, now_mono - self._health_failure_since), 1) if self._health_failure_since is not None else None,
                "decision_tracks": dict(self._decision_tracks),
                "spatial_mapping": self._homography.status(self._last_frame_size or ((info.width, info.height) if info else None)),
                "spatial_tracks": dict(self._spatial_tracks),
                "decision_engine": "single_source",
                "profile": profile_name(),
                "zone_id": CAMERA_ZONE_ID,
                "zone_period": self.zone_period,
                "warning_person_ids": list(self.warning_person_ids),
                "review_person_ids": list(self.review_person_ids),
                "alarm_person_ids": list(self.alarm_person_ids),
                "tracked_person_ids": list(self.tracked_person_ids),
                "authorized_track_ids": sorted(self._authorized_tracks),
                "last_event": self.last_event,
                "last_frame_at": self.last_frame_at,
                "dwell_threshold_seconds": DWELL_SECONDS,
                "heatmap_half_life_seconds": HEATMAP_HALF_LIFE_SECONDS,
                "events_with_evidence": sum(1 for event in self._events if event.get("evidence_url")),
            }

    # ---------------------------------------------------------------- khung hình cho stream/snapshot
    def wait_for_frame(self, last_seq: int = 0, timeout: float = 2.0) -> tuple[int, bytes] | None:
        """Chờ frame đã annotate mới hơn `last_seq`. Dùng cho MJPEG stream."""
        with self._out_cond:
            self._out_cond.wait_for(lambda: self._out_seq != last_seq or self._stop.is_set(), timeout=timeout)
            if self._stop.is_set():
                return None
            if self._out_jpeg is None or self._out_seq == last_seq:
                return None
            return self._out_seq, self._out_jpeg

    def latest_jpeg(self) -> bytes | None:
        with self._out_cond:
            return self._out_jpeg

    def snapshot_jpeg(self, annotated: bool = False) -> bytes | None:
        """Ảnh chụp hiện tại. annotated=False -> frame gốc (dùng để vẽ vùng cấm đúng khung nhìn)."""
        if annotated:
            return self.latest_jpeg()
        with self._raw_cond:
            frame = self._raw
        if frame is None:
            return None
        ok, jpeg = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
        return jpeg.tobytes() if ok else None

    def read_jpeg(self) -> bytes | None:
        """Tương thích API cũ: trả frame đã annotate mới nhất (tự start worker nếu cần)."""
        self.start()
        result = self.wait_for_frame(0, timeout=2.0)
        return result[1] if result else self.latest_jpeg()

    # ---------------------------------------------------------------- luồng đọc camera
    def _capture_loop(self) -> None:
        cap: OpenedCamera | None = None
        backoff, failures = 1.0, 0
        try:
            while not self._stop.is_set():
                if cap is None:
                    cap = open_camera(self._source_spec, width=FRAME_WIDTH, height=FRAME_HEIGHT,
                                      fourcc=CAMERA_FOURCC, scan_max_index=CAMERA_SCAN_MAX)
                    if cap is None:
                        error = (
                            f"Không mở được camera (CAMERA_INDEX={self._source_spec}). Chạy "
                            "`python -m ai.list_cameras` để tìm index đúng, đóng app khác đang dùng camera, "
                            "hoặc thử cổng USB khác.")
                        with self._lock:
                            self._camera_info = None
                        self._set_camera_health(False, error)
                        logger.warning("%s", error)
                        self._stop.wait(backoff)
                        backoff = min(10.0, backoff * 1.7)
                        continue
                    backoff, failures = 1.0, 0
                    with self._lock:
                        self._camera_info = cap
                    # Do not mark ONLINE on open alone. _publish_raw promotes health
                    # only after the configured stable-frame window is satisfied.
                    self._publish_raw(cap.first_frame)
                ok, frame = cap.capture.read()
                if not ok or frame is None or not frame.size:
                    failures += 1
                    if failures >= 30:  # ~ vài giây liên tục không có frame -> mở lại camera
                        logger.warning("Mất tín hiệu camera %s; đang mở lại", cap.describe())
                        cap.capture.release()
                        cap = None
                        with self._lock:
                            self._camera_info = None
                        self._set_camera_health(False, "Mất tín hiệu camera, đang thử kết nối lại...")
                    else:
                        time.sleep(0.03)
                    continue
                failures = 0
                self._publish_raw(frame)
        except Exception:  # noqa: BLE001
            logger.exception("Luồng đọc camera bị lỗi")
            self._set_camera_health(False, "Luồng đọc camera bị lỗi; xem log server.")
        finally:
            if cap is not None:
                cap.capture.release()

    def _camera_frames_stable_locked(self, now: float) -> bool:
        """Check the recent frame cadence; caller holds _lock."""
        if now - self._last_raw_at >= CAMERA_FRAME_STALE_SECONDS:
            return False
        times = list(self._camera_frame_times)
        if len(times) < CAMERA_RECOVERY_MIN_FRAMES:
            return False
        newest = times[-1]
        if now - newest >= CAMERA_FRAME_STALE_SECONDS:
            return False
        earliest = newest
        count = 1
        for index in range(len(times) - 2, -1, -1):
            gap = times[index + 1] - times[index]
            if gap < 0 or gap > CAMERA_RECOVERY_MAX_FRAME_GAP_SECONDS:
                break
            earliest = times[index]
            count += 1
            if newest - earliest >= CAMERA_RECOVERY_STABLE_SECONDS:
                return count >= CAMERA_RECOVERY_MIN_FRAMES
        return False

    def _camera_instability_since_locked(self, now: float) -> float:
        """Estimate when the current cadence first crossed the 0.5s gap limit; caller holds _lock."""
        times = list(self._camera_frame_times)
        if len(times) >= 2 and times[-1] - times[-2] > CAMERA_RECOVERY_MAX_FRAME_GAP_SECONDS:
            return times[-2] + CAMERA_RECOVERY_MAX_FRAME_GAP_SECONDS
        if times and now - times[-1] > CAMERA_RECOVERY_MAX_FRAME_GAP_SECONDS:
            return times[-1] + CAMERA_RECOVERY_MAX_FRAME_GAP_SECONDS
        return float(now)

    def _camera_stream_stable_locked(self, now: float) -> bool:
        """Single source of truth for status, watchdog and RFID; caller holds _lock."""
        return self._camera_health is not False and self._camera_frames_stable_locked(now)

    def _publish_raw(self, frame: np.ndarray) -> None:
        now = time.monotonic()
        with self._raw_cond:
            if self._capture_last_tick:
                instantaneous = 1.0 / max(1e-3, now - self._capture_last_tick)
                self._capture_fps = (0.9 * self._capture_fps + 0.1 * instantaneous) if self._capture_fps else instantaneous
            self._capture_last_tick = now
            self._raw = frame
            self._raw_seq += 1
            self._last_raw_at = now
            self._raw_cond.notify_all()
        should_mark_online = False
        with self._lock:
            self._camera_frame_times.append(now)
            cutoff = now - CAMERA_FRAME_HISTORY_SECONDS
            while len(self._camera_frame_times) > 1 and self._camera_frame_times[0] < cutoff:
                self._camera_frame_times.popleft()
            frame_cadence_stable = self._camera_frames_stable_locked(now)
            if not frame_cadence_stable:
                self._authorized_tracks.clear()
                self._rfid_tickets.clear()
            should_mark_online = (self._camera_health is not True and frame_cadence_stable)
        if should_mark_online:
            # Reuse the one transition path: it revokes all pre-outage credentials,
            # accounts for outage duration and emits camera_recovered exactly once.
            self._set_camera_health(True)

    # ---------------------------------------------------------------- luồng AI
    def _load_model(self) -> None:
        if self._model is not None:
            return
        with self._lock:
            self._model_loading = True
        try:
            from ultralytics import YOLO

            self._model = YOLO(YOLO_WEIGHTS)
            logger.info("Loaded model %s; ByteTrack enabled", YOLO_WEIGHTS)
            with self._lock:
                self._model_error = None
        except Exception as exc:  # noqa: BLE001
            logger.exception("Không nạp được YOLO; cài ai/requirements.txt và kiểm tra file weights")
            with self._lock:
                self._model_error = f"{type(exc).__name__}: {exc}"[:300]
        finally:
            with self._lock:
                self._model_loading = False

    def _process_loop(self) -> None:
        self._load_model()
        last_seq, last_tick, fps_ema = 0, time.monotonic(), 0.0
        retry_delay = 2.0
        next_model_retry = time.monotonic() + retry_delay
        while not self._stop.is_set():
            if self._model is None and time.monotonic() >= next_model_retry:
                self._load_model()
                if self._model is not None:
                    retry_delay = 2.0
                else:
                    retry_delay = min(60.0, retry_delay * 2.0)
                next_model_retry = time.monotonic() + retry_delay
            with self._raw_cond:
                self._raw_cond.wait_for(lambda: self._raw_seq != last_seq or self._stop.is_set(), timeout=1.0)
                if self._stop.is_set():
                    break
                if self._raw_seq == last_seq or self._raw is None:
                    continue
                frame, last_seq = self._raw, self._raw_seq
                frame_captured_at = self._last_raw_at
            process_started = time.monotonic()
            try:
                jpeg = self._process_frame(frame)
                with self._lock:
                    self._last_processed_at = time.monotonic()
                    self._last_process_error = None
            except Exception as exc:  # noqa: BLE001
                logger.exception("Lỗi khi xử lý frame (AI/vẽ/mã hóa)")
                with self._lock:
                    self._last_process_error = f"{type(exc).__name__}: {exc}"[:300]
                jpeg = None
            tick = time.monotonic()
            fps_ema = 0.9 * fps_ema + 0.1 / max(1e-3, tick - last_tick) if fps_ema else 1.0 / max(1e-3, tick - last_tick)
            self._fps, last_tick = fps_ema, tick
            with self._lock:
                self._process_latency_ms = max(0.0, tick - frame_captured_at) * 1000.0

    def _revoke_rfid_on_camera_stall(self, now: float) -> bool:
        """Fail closed when the frame watchdog detects a stale camera, even if health stayed True.

        This is a code-level watchdog guarantee; it does not assert that a physical
        camera driver's blocking read has been observed on hardware.
        """
        with self._lock:
            # Credential safety follows the 0.5s stable-frame predicate, not the 3s
            # offline-event threshold. A short hiccup therefore revokes access at once.
            camera_stable = self._camera_stream_stable_locked(now)
            if not camera_stable:
                self._authorized_tracks.clear()
                self._rfid_tickets.clear()
            # Startup grace applies only before the first successful frame. Once the
            # camera has produced a frame (health=True), a later stall revokes RFID
            # immediately; camera_offline is still emitted at the hard stale threshold.
            startup_grace = (self._started_at > 0 and now - self._started_at < STARTUP_GRACE_SECONDS
                             and self._last_raw_at <= 0.0)
            stale = now - self._last_raw_at >= CAMERA_FRAME_STALE_SECONDS
            should_transition = stale and not startup_grace and self._camera_health is not False
        if should_transition:
            self._set_camera_health(False, "Không nhận được frame camera trong thời gian watchdog cho phép.")
        return (not camera_stable) or should_transition

    def _health_watchdog_tick(self, now: float | None = None) -> None:
        """One deterministic watchdog pass; notification debounce never weakens RFID gating."""
        now = time.monotonic() if now is None else float(now)
        self._revoke_rfid_on_camera_stall(now)
        with self._lock:
            startup_grace = self._started_at > 0 and now - self._started_at < STARTUP_GRACE_SECONDS
            camera_ok = self._camera_stream_stable_locked(now)
            camera_frame_fresh = (now - self._last_raw_at) < CAMERA_FRAME_STALE_SECONDS
            model_ok = self._model is not None
            process_ok = (now - self._last_processed_at) < 3.0
            ai_ok = model_ok and process_ok
            failure = None if camera_ok and ai_ok else (
                "camera_offline" if not camera_frame_fresh else "camera_unstable" if not camera_ok
                else "ai_model_unavailable" if not model_ok else "ai_processing_stalled")
            if startup_grace:
                failure = None

            if failure is None:
                if self._health_event_active and not self._camera_offline_event_reported:
                    self._emit("system_health_recovered", -1, "Camera/AI đã phục hồi.", severity="info")
                self._health_event_active = False
                self._health_failure_since = None
                self._health_condition_since = None
                self._health_reason = None
                self._health_alarm_owned = False
            else:
                previous_reason = self._health_reason
                if self._health_condition_since is None:
                    # Debounce clock is independent from arming; offline is anchored to last good frame.
                    if failure == "camera_offline" and self._last_raw_at > 0:
                        self._health_condition_since = self._last_raw_at + CAMERA_RECOVERY_MAX_FRAME_GAP_SECONDS
                    elif failure == "camera_unstable":
                        self._health_condition_since = self._camera_instability_since_locked(now)
                    else:
                        self._health_condition_since = now
                if self.anti_theft_enabled and self._health_failure_since is None:
                    self._health_failure_since = self._health_condition_since
                elif not self.anti_theft_enabled:
                    self._health_failure_since = None
                elif previous_reason == "camera_unstable" and failure == "camera_offline":
                    # Preserve the original health escalation onset across the offline transition.
                    pass
                self._health_reason = failure

                if failure == "camera_offline":
                    if not self._camera_offline_event_reported:
                        self._emit("camera_offline", -1, "Camera USB bên ngoài mất kết nối.",
                                   severity="critical", camera_role="external_usb")
                        self._camera_offline_event_reported = True
                    self._health_event_active = True
                elif failure == "camera_unstable":
                    elapsed = max(0.0, now - (self._health_condition_since or now))
                    if elapsed >= CAMERA_UNSTABLE_DELAY_SECONDS and not self._health_event_active:
                        frame_times = list(self._camera_frame_times)
                        gaps = [b - a for a, b in zip(frame_times, frame_times[1:])]
                        max_gap = max(gaps, default=0.0)
                        logger.warning(
                            "Camera USB liên tục không đạt cadence ổn định: capture_fps=%.2f, max_frame_gap=%.3fs, delay=%.2fs; yêu cầu khoảng 3 FPS trở lên.",
                            self._capture_fps, max_gap, CAMERA_UNSTABLE_DELAY_SECONDS)
                        self._emit("camera_unstable", -1,
                                   "Camera USB có khoảng cách frame vượt 0,5 giây kéo dài.",
                                   severity="warning", health_reason="camera_unstable",
                                   capture_fps=round(self._capture_fps, 2),
                                   max_frame_gap_seconds=round(max_gap, 3),
                                   unstable_seconds=round(elapsed, 2))
                        self._health_event_active = True
                else:
                    if not self._health_event_active:
                        self._emit(failure, -1, f"Sức khỏe hệ thống không đạt: {failure}.", severity="critical")
                        self._health_event_active = True

                if not self.anti_theft_enabled:
                    self._health_failure_since = None
                health_decision = self._evaluate_decision_engine([], now)
                health_active = bool(self.anti_theft_enabled and self._health_failure_since is not None
                                     and (failure != "camera_unstable"
                                          or now - self._health_failure_since >= CAMERA_UNSTABLE_DELAY_SECONDS))
                for item in health_decision.events:
                    if item.get("type") == "alarm_state_changed":
                        self._emit("alarm_state_changed", -1, f"Trạng thái an ninh: {item.get('state')}.",
                                   severity=item.get("severity", "info"), alarm_state=item.get("state"),
                                   reason="health_fault" if health_active else None,
                                   health_reason=self._health_reason if health_active else None)
                self._health_alarm_owned = bool(health_active and self.alarm_state == "ALARM")

    def _health_watchdog_loop(self) -> None:
        """Independent 1-second watchdog; detects capture stalls and AI/model failures."""
        while not self._stop.wait(1.0):
            self._health_watchdog_tick()

    def _render_loop(self) -> None:
        """Phát video theo nhịp riêng, không bắt trình duyệt chờ YOLO xử lý xong từng frame."""
        interval = 1.0 / STREAM_FPS
        last_raw_seq = -1
        last_tick = time.monotonic()
        fps_ema = 0.0
        while not self._stop.is_set():
            started = time.monotonic()
            with self._raw_cond:
                self._raw_cond.wait_for(
                    lambda: self._raw_seq != last_raw_seq or self._stop.is_set(),
                    timeout=interval,
                )
                if self._stop.is_set():
                    break
                if self._raw is None or self._raw_seq == last_raw_seq:
                    continue
                frame = self._raw.copy()
                last_raw_seq = self._raw_seq
            with self._lock:
                state = self._display_state
            if state is None:
                detections: list[dict[str, Any]] = []
                zone = self.zone
                height, width = frame.shape[:2]
                poly_i = np.round(zone_to_pixels(zone, width, height)).astype(np.int32)
                alarm, authorized = False, set()
            else:
                detections, poly_i, alarm, authorized = state
                # Copy mutable containers so drawing never shares state with the AI worker.
                detections = [dict(item) for item in detections]
                authorized = set(authorized)
            jpeg = self._render(frame, detections, poly_i, alarm, authorized, quality=STREAM_JPEG_QUALITY)
            if jpeg is not None:
                with self._out_cond:
                    self._out_jpeg = jpeg
                    self._out_seq += 1
                    self._out_cond.notify_all()
            now = time.monotonic()
            fps_ema = (0.9 * fps_ema + 0.1 / max(1e-3, now - last_tick)) if fps_ema else 1.0 / max(1e-3, now - last_tick)
            self._stream_fps, last_tick = fps_ema, now
            remaining = interval - (time.monotonic() - started)
            if remaining > 0:
                self._stop.wait(remaining)

    def _detect(self, frame: np.ndarray) -> list[dict[str, Any]]:
        """Chạy YOLO (+ByteTrack). Trả về danh sách {'box','conf','id'}; id có thể None."""
        if self._model is None:
            return []
        kwargs = dict(classes=[0], device=AI_DEVICE, conf=CONFIDENCE, imgsz=IMAGE_SIZE, verbose=False)
        try:
            if self._tracking_enabled:
                results = self._model.track(source=frame, persist=True, tracker="bytetrack.yaml", **kwargs)
            else:
                results = self._model.predict(source=frame, **kwargs)
        except Exception:  # noqa: BLE001
            if not self._tracking_enabled:
                raise
            logger.exception("ByteTrack lỗi (thiếu thư viện `lapx`?); chuyển sang chỉ phát hiện, không có ID")
            self._tracking_enabled = False
            results = self._model.predict(source=frame, **kwargs)
        detections: list[dict[str, Any]] = []
        boxes = results[0].boxes if results else None
        if boxes is None or len(boxes) == 0:
            return detections
        xyxy = boxes.xyxy.cpu().numpy()
        confs = boxes.conf.cpu().numpy()
        ids = boxes.id.int().cpu().tolist() if getattr(boxes, "id", None) is not None else [None] * len(xyxy)
        for (x1, y1, x2, y2), conf, tid in zip(xyxy.tolist(), confs.tolist(), ids):
            detections.append({"box": (float(x1), float(y1), float(x2), float(y2)), "conf": float(conf),
                               "id": int(tid) if tid is not None else None})
        return detections

    def _try_bind_rfid_tickets(self, detections: list[dict[str, Any]], now: float,
                               frame_size: tuple[int, int]) -> None:
        """Auto-bind only an unambiguous swipe-time candidate when explicitly enabled.

        The candidate set is snapshotted when RC522 creates the ticket. A new, missing,
        or changed candidate during the stability interval blocks auto-binding permanently.
        """
        if not RFID_AUTO_BIND_ENABLED or not self.rfid_entry_roi:
            return
        if not self._camera_stream_stable_locked(now):
            self._authorized_tracks.clear()
            self._rfid_tickets.clear()
            return
        self._prune_rfid_tickets_locked(now)
        if len(self._rfid_tickets) != 1:
            for ticket in self._rfid_tickets.values():
                ticket["auto_bind_blocked"] = True
                ticket["bind_candidate_track_id"] = None
                ticket["bind_candidate_since"] = None
            return
        uid, ticket = next(iter(self._rfid_tickets.items()))
        if ticket.get("auto_bind_blocked"):
            return
        snapshot = ticket.get("bind_snapshot_track_ids", [])
        if len(snapshot) != 1:
            ticket["auto_bind_blocked"] = True
            return
        width, height = frame_size
        roi = np.array([[(int(x * width), int(y * height)) for x, y in self.rfid_entry_roi]], dtype=np.int32)
        current_ids: set[int] = set()
        roi_detections = []
        for det in detections:
            x1, y1, x2, y2 = map(float, det["box"])
            center = (int((x1 + x2) / 2), int((y1 + y2) / 2))
            if cv2.pointPolygonTest(roi[0], center, False) >= 0:
                roi_detections.append(det)
                if det.get("id") is not None:
                    current_ids.add(int(det["id"]))
        expected = int(snapshot[0])
        if (len(roi_detections) != 1 or current_ids != {expected}
                or expected in self._authorized_tracks):
            ticket["auto_bind_blocked"] = True
            ticket["bind_candidate_track_id"] = None
            ticket["bind_candidate_since"] = None
            return
        candidate_since = ticket.get("bind_candidate_since")
        last_observed_at = ticket.get("bind_last_observed_at")
        if candidate_since is None or last_observed_at is None:
            ticket["auto_bind_blocked"] = True
            return
        observation_gap = now - float(last_observed_at)
        if observation_gap > RFID_BIND_MAX_OBSERVATION_GAP_SECONDS:
            ticket["auto_bind_blocked"] = True
            ticket["bind_candidate_track_id"] = None
            return
        if observation_gap > 1e-6:
            ticket["bind_observation_count"] = int(ticket.get("bind_observation_count", 1)) + 1
            ticket["bind_last_observed_at"] = now
        if (int(ticket.get("bind_observation_count", 1)) < 2
                or now - float(ticket.get("created_at", candidate_since)) < RFID_BIND_STABILITY_SECONDS):
            return
        self._authorized_tracks[expected] = {"uid": uid, "name": ticket.get("name"), "at": now,
            "allowed_zones": list(ticket.get("allowed_zones", []))}
        self._rfid_tickets.pop(uid, None)
        self._emit("rfid_ticket_bound", expected,
            f"RFID ticket ****{str(uid)[-4:]} được ghép tự động với Track {expected} trong vùng cửa.",
            severity="info", authorized=True, card_uid=uid,
            binding_method="swipe_time_single_candidate_snapshot")

    @staticmethod
    def _box_iou(a: Sequence[float], b: Sequence[float]) -> float:
        ax1, ay1, ax2, ay2 = map(float, a)
        bx1, by1, bx2, by2 = map(float, b)
        ix1, iy1, ix2, iy2 = max(ax1, bx1), max(ay1, by1), min(ax2, bx2), min(ay2, by2)
        inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
        area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
        area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
        union = area_a + area_b - inter
        return inter / union if union > 0 else 0.0

    def _handover_authorizations(self, detections: list[dict[str, Any]], now: float) -> None:
        """RFID authorization is never transferred using geometry alone.

        ByteTrack/Decision Engine may preserve a behavioral session, but a new Track ID
        must be explicitly authenticated with a fresh, one-use RFID ticket.
        """
        return

    @staticmethod
    def _track_paths_cross(previous_a: Sequence[float], current_a: Sequence[float],
                           previous_b: Sequence[float], current_b: Sequence[float]) -> bool:
        """Return whether two Track center paths intersect between consecutive frames."""
        def center(box: Sequence[float]) -> tuple[float, float]:
            x1, y1, x2, y2 = map(float, box)
            return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)

        a1, a2, b1, b2 = center(previous_a), center(current_a), center(previous_b), center(current_b)

        def orient(p: tuple[float, float], q: tuple[float, float], r: tuple[float, float]) -> float:
            return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])

        def on_segment(p: tuple[float, float], q: tuple[float, float], r: tuple[float, float]) -> bool:
            return (min(p[0], r[0]) <= q[0] <= max(p[0], r[0])
                    and min(p[1], r[1]) <= q[1] <= max(p[1], r[1]))

        o1, o2, o3, o4 = orient(a1, a2, b1), orient(a1, a2, b2), orient(b1, b2, a1), orient(b1, b2, a2)
        eps = 1e-6
        if ((o1 > eps and o2 < -eps or o1 < -eps and o2 > eps)
                and (o3 > eps and o4 < -eps or o3 < -eps and o4 > eps)):
            return True
        return ((abs(o1) <= eps and on_segment(a1, b1, a2))
                or (abs(o2) <= eps and on_segment(a1, b2, a2))
                or (abs(o3) <= eps and on_segment(b1, a1, b2))
                or (abs(o4) <= eps and on_segment(b1, a2, b2)))

    def _revoke_authorizations_on_track_overlap(self, detections: list[dict[str, Any]]) -> None:
        """Revoke RFID when an authorized Track overlaps or crosses another live Track."""
        by_id = {int(det["id"]): det for det in detections if det.get("id") is not None}
        for authorized_id in list(self._authorized_tracks):
            authorized_det = by_id.get(int(authorized_id))
            if authorized_det is None:
                continue
            previous_auth = self._track_state.get(int(authorized_id), {}).get("last_box")
            for other_id, other_det in by_id.items():
                if other_id == int(authorized_id):
                    continue
                overlap = self._box_iou(authorized_det["box"], other_det["box"])
                previous_other = self._track_state.get(other_id, {}).get("last_box")
                crossed = bool(previous_auth and previous_other and self._track_paths_cross(
                    previous_auth, authorized_det["box"], previous_other, other_det["box"]))
                if overlap >= RFID_TRACK_OVERLAP_REVOKE_IOU or crossed:
                    auth = self._authorized_tracks.pop(int(authorized_id), None)
                    if auth:
                        reason = "track_crossing" if crossed else "track_overlap"
                        self._emit("authorization_revoked", int(authorized_id),
                            f"Quyền RFID của Track {authorized_id} bị thu hồi do giao cắt/chồng lấn với Track {other_id}.",
                            severity="warning", authorized=False, card_uid=auth.get("uid"),
                            reason=reason, conflicting_track_id=int(other_id),
                            overlap_iou=round(overlap, 3))
                    break

    def _update_tracks(self, detections: list[dict[str, Any]], now: float) -> tuple[list[int], list[int]]:
        """Time-based zone hysteresis; behavior is independent of camera FPS."""
        self._handover_authorizations(detections, now)
        self._revoke_authorizations_on_track_overlap(detections)
        entered: list[int] = []
        exited: list[int] = []
        seen: set[int] = set()
        for det in detections:
            tid = det["id"]
            if tid is None:
                det["inside"] = det["raw_inside"]
                continue
            seen.add(tid)
            st = self._track_state.setdefault(tid, {"inside": False, "last_seen_at": now,
                                                    "inside_candidate_since": None,
                                                    "outside_candidate_since": None})
            st["last_seen_at"] = now
            st["last_box"] = tuple(float(v) for v in det["box"])
            if det["raw_inside"] or (st["inside"] and bool(det.get("exit_boundary_inside"))):
                st["outside_candidate_since"] = None
                if not st["inside"]:
                    if st.get("inside_candidate_since") is None:
                        st["inside_candidate_since"] = now
                    if now - float(st["inside_candidate_since"]) >= ENTER_CONFIRM_SECONDS:
                        st["inside"] = True
                        st["inside_candidate_since"] = None
                        entered.append(tid)
            else:
                st["inside_candidate_since"] = None
                if st["inside"]:
                    if st.get("outside_candidate_since") is None:
                        st["outside_candidate_since"] = now
                    if now - float(st["outside_candidate_since"]) >= EXIT_CONFIRM_SECONDS:
                        st["inside"] = False
                        st["outside_candidate_since"] = None
                        exited.append(tid)
            det["inside"] = bool(st["inside"])
        for tid in list(self._track_state):
            if tid in seen:
                continue
            st = self._track_state[tid]
            missing_age = now - float(st.get("last_seen_at", now))
            if missing_age > RFID_TRACK_AUTH_LOSS_SECONDS:
                auth = self._authorized_tracks.pop(tid, None)
                if auth:
                    self._emit("authorization_revoked", tid,
                        f"Quyền RFID của Track {tid} bị thu hồi vì Track không còn được xác nhận.",
                        severity="warning", authorized=False, card_uid=auth.get("uid"),
                        reason="track_lost", missing_seconds=round(missing_age, 3))
            if missing_age > TRACK_HOLD_SECONDS:
                if st["inside"]:
                    exited.append(tid)
                del self._track_state[tid]
                self._authorized_tracks.pop(tid, None)
        return entered, exited

    def _apply_events(self, entered: list[int], exited: list[int], now: float) -> None:
        # Vào/ra vùng là các sự kiện theo vòng đời track, không phát lại mỗi frame.
        for tid in sorted(entered):
            self._inside_since[tid] = now
            auth = self._authorized_tracks.get(tid)
            if auth and CAMERA_ZONE_ID in auth.get("allowed_zones", []):
                self._emit("zone_entry", tid, f"Người ID {tid} đi vào vùng được cấp quyền.",
                           severity="low", authorized=True, card_uid=auth.get("uid"), zone=CAMERA_ZONE_ID)
            elif auth:
                self._emit("zone_entry", tid, f"Người ID {tid} đi vào vùng không nằm trong quyền của thẻ.",
                           severity="warning", authorized=False, card_uid=auth.get("uid"), zone=CAMERA_ZONE_ID)
            elif self.anti_theft_enabled:
                self._emit("zone_entry", tid, f"Người ID {tid} đi vào vùng bảo vệ; đang chờ xác thực.",
                           severity="info", authorized=False, access_pending=True)
            else:
                self._emit("zone_entry", tid, f"Người ID {tid} đi vào vùng khi chống trộm đang tắt.",
                           severity="info", authorized=False, security_armed=False)
        for tid, st in self._track_state.items():
            if not st["inside"]:
                continue
            elapsed = now - self._inside_since.setdefault(tid, now)
            if elapsed >= DWELL_SECONDS and tid not in self._dwell_alerted:
                auth = self._authorized_tracks.get(tid)
                self._emit("long_dwell", tid, f"Người ID {tid} ở trong vùng {int(elapsed)} giây.",
                           severity="medium", authorized=bool(auth),
                           card_uid=auth.get("uid") if auth else None, dwell_seconds=round(elapsed, 1))
                self._dwell_alerted.add(tid)
        for tid in exited:
            started = self._inside_since.pop(tid, None)
            duration = max(0.0, now - started) if started is not None else None
            auth = self._authorized_tracks.get(tid)
            self._emit("zone_exit", tid, f"Người ID {tid} rời vùng bảo vệ.",
                       severity="low", authorized=bool(auth), dwell_seconds=round(duration, 1) if duration is not None else None)
            self._dwell_alerted.discard(tid)
            # Leaving the polygon is not the end of the tracked person; retain card authorization.
        for tid, auth in list(self._authorized_tracks.items()):
            if now - float(auth.get("at", now)) >= AUTH_MAX_SECONDS:
                self._authorized_tracks.pop(tid, None)
                self._emit("authorization_expired", tid,
                           f"Quyền xác thực của Track {tid} đã hết thời hạn tối đa.",
                           severity="medium", authorized=False,
                           card_uid=auth.get("uid"), reason="auth_max_seconds",
                           auth_max_seconds=AUTH_MAX_SECONDS)

    def _is_outward_frame_exit(self, det: dict[str, Any], now: float,
                               width: int, height: int) -> bool:
        """Detect a genuine outward crossing using history from before the edge band.

        The history is updated on every detection, not only near an image edge.
        A missing/short history is intentionally permissive (handover remains possible).
        """
        tid = det.get("id")
        if tid is None:
            return False
        x1, y1, x2, y2 = map(float, det["box"])
        state = self._track_state.setdefault(int(tid), {"inside": False, "last_seen_at": now,
            "inside_candidate_since": None, "outside_candidate_since": None})
        samples = list(state.get("frame_motion_samples", []))
        samples.append((float(now), (x1, y1, x2, y2)))
        samples = [(stamp, box) for stamp, box in samples
                   if now - stamp <= HANDOVER_EDGE_HISTORY_SECONDS]
        state["frame_motion_samples"] = samples[-max(HANDOVER_EDGE_MIN_SAMPLES, 12):]

        margin_x = width * HANDOVER_EDGE_MARGIN_RATIO
        margin_y = height * HANDOVER_EDGE_MARGIN_RATIO
        edges = []
        if x1 <= margin_x:
            edges.append(("left", 0, -1.0, width))
        if x2 >= width - margin_x:
            edges.append(("right", 2, 1.0, width))
        if y1 <= margin_y:
            edges.append(("top", 1, -1.0, height))
        if y2 >= height - margin_y:
            edges.append(("bottom", 3, 1.0, height))
        if not edges:
            det["exited_frame_edge"] = False
            return False

        if (len(samples) < HANDOVER_EDGE_MIN_SAMPLES or
                samples[-1][0] - samples[0][0] < HANDOVER_EDGE_MIN_SPAN_SECONDS):
            det["exited_frame_edge"] = False
            return False

        for edge, _coordinate_index, outward_sign, dimension in edges:
            # Side/top clipping pins the leading bbox edge at the image boundary.
            # Use the body center so the remaining visible body still contributes motion.
            # At the bottom, use the footpoint as requested, but discard samples already
            # clipped at the frame edge and extrapolate from the last visible footpoints.
            if edge == "left":
                # The right/trailing edge remains measurable while the left edge is clipped.
                trajectory = [(stamp, box[2]) for stamp, box in samples]
            elif edge == "right":
                # The left/trailing edge remains measurable while the right edge is clipped.
                trajectory = [(stamp, box[0]) for stamp, box in samples]
            elif edge == "top":
                # The lower/trailing edge remains measurable while the top is clipped.
                trajectory = [(stamp, box[3]) for stamp, box in samples]
            else:
                trajectory = [(stamp, box[3]) for stamp, box in samples if box[3] < height - 1.0]
                # Once the feet are clipped, the footpoint is pinned at the frame edge.
                # Fall back to the visible upper body edge only when too few valid feet remain.
                if len(trajectory) < HANDOVER_EDGE_MIN_SAMPLES:
                    trajectory = [(stamp, box[1]) for stamp, box in samples]
            if len(trajectory) < HANDOVER_EDGE_MIN_SAMPLES:
                continue
            elapsed = trajectory[-1][0] - trajectory[0][0]
            if elapsed < HANDOVER_EDGE_MIN_SPAN_SECONDS:
                continue

            # Estimate motion with least-squares slope over the full history.
            # First/last-frame subtraction is too sensitive to ordinary YOLO jitter.
            times = np.asarray([sample[0] for sample in trajectory], dtype=np.float64)
            values = np.asarray([sample[1] for sample in trajectory], dtype=np.float64)
            centered_times = times - float(times.mean())
            denominator = float(np.dot(centered_times, centered_times))
            if denominator <= 1e-9:
                continue
            slope_px_per_second = float(np.dot(centered_times, values - values.mean()) / denominator)
            outward_speed = slope_px_per_second * outward_sign
            estimated_displacement = outward_speed * elapsed
            speed_ratio = outward_speed / max(1.0, float(dimension))
            if (speed_ratio >= HANDOVER_EDGE_OUTWARD_SPEED_RATIO and
                    estimated_displacement >= HANDOVER_EDGE_MIN_DISPLACEMENT_PX):
                det["exited_frame_edge"] = True
                return True
        det["exited_frame_edge"] = False
        return False

    def _process_frame(self, frame: np.ndarray) -> bytes | None:
        now = time.monotonic()
        self._maybe_reload_zone(now)
        height, width = frame.shape[:2]
        with self._lock:
            self._last_frame_size = (width, height)
            zone, zone_size = self.zone, self._zone_frame_size
        period = current_zone_period()
        period_factor = 1.15 if period == "night" else 1.0
        alarm_zone = scale_zone(zone, period_factor)
        warning_zone = scale_zone(zone, period_factor * 1.12)
        poly = zone_to_pixels(alarm_zone, width, height)
        poly_i = np.round(poly).astype(np.int32)
        warning_poly = zone_to_pixels(warning_zone, width, height)
        exit_buffer_px = ZONE_EXIT_BUFFER_RATIO * min(width, height)

        # AI nhìn frame SẠCH (bản cũ vẽ vùng lên frame rồi mới đưa cho YOLO).
        detections = self._detect(frame)
        detections = [d for d in detections
                      if (d["box"][3] - d["box"][1]) / height >= MIN_BOX_HEIGHT_RATIO]
        with self._lock:
            self._detection_count = len(detections)
        mask = self._zone_mask(width, height, alarm_zone, poly_i) if ZONE_MODE == "overlap" else None
        for det in detections:
            x1, y1, x2, y2 = det["box"]
            det["normalized_footpoint"] = [((x1 + x2) / 2.0) / max(1, width), y2 / max(1, height)]
            det["raw_inside"] = is_box_in_zone(det["box"], (width, height), poly, ZONE_MODE, mask,
                                               ZONE_OVERLAP_MIN, TRUNCATED_FALLBACK)
            det["raw_warning"] = is_box_in_zone(det["box"], (width, height), warning_poly, "foot",
                                                None, ZONE_OVERLAP_MIN, TRUNCATED_FALLBACK)
            foot_x = float(det["normalized_footpoint"][0]) * max(1, width - 1)
            foot_y = float(det["normalized_footpoint"][1]) * max(1, height - 1)
            signed_distance = cv2.pointPolygonTest(poly_i, (foot_x, foot_y), True)
            det["exit_boundary_inside"] = signed_distance >= -exit_buffer_px
            # A static box touching an image edge is not evidence of leaving.
            # Require outward movement measured from recent box-edge samples.
            self._is_outward_frame_exit(det, now, width, height)

        with self._lock:
            event_ids_before = {str(event.get("event_id")) for event in self._events}
            # Heatmap có suy giảm theo thời gian để phản ánh khu vực hoạt động gần đây.
            dt = max(0.0, now - self._heatmap_last_tick)
            self._heatmap *= float(np.exp(-np.log(2.0) * dt / HEATMAP_HALF_LIFE_SECONDS))
            self._heatmap_last_tick = now
            for det in detections:
                x1, y1, x2, y2 = det["box"]
                px = min(HEATMAP_WIDTH - 1, max(0, int(((x1 + x2) / 2.0) / max(1, width) * HEATMAP_WIDTH)))
                py = min(HEATMAP_HEIGHT - 1, max(0, int(y2 / max(1, height) * HEATMAP_HEIGHT)))
                self._heatmap[py, px] += 1.0
            self._last_detections = [{"id": det.get("id"), "box": tuple(det["box"])} for det in detections]
            self._last_detection_at = now
            self._try_bind_rfid_tickets(detections, now, (width, height))
            entered, exited = self._update_tracks(detections, now)
            alarm_ids = sorted({int(d["id"]) for d in detections if d["inside"] and d["id"] is not None})
            warning_ids = sorted({int(d["id"]) for d in detections
                                  if d["raw_warning"] and d["id"] is not None
                                  and not d["inside"]})
            self.person_in_zone = any(d["inside"] for d in detections)
            self.alarm_person_ids = alarm_ids
            self.warning_person_ids = warning_ids
            self.tracked_person_ids = sorted({d["id"] for d in detections if d["id"] is not None})
            self.last_frame_at = datetime.now(BUSINESS_TZ).isoformat(timespec="seconds")
            self.zone_period = period
            authorized = {int(tid) for tid, item in self._decision_tracks.items()
                          if item.get("state") == "AUTHORIZED"}
            observations = self._build_decision_observations(now, detections)
            # Anonymous detections cannot inherit RFID authorization; fail closed.
            anonymous_inside = any(d.get("inside") and d.get("id") is None for d in detections)
            health_elapsed = (max(0.0, now - self._health_failure_since)
                              if self._health_failure_since is not None else 0.0)
            health_fault = bool(self.anti_theft_enabled and self._health_failure_since is not None
                                and (self._health_reason != "camera_unstable"
                                     or health_elapsed >= CAMERA_UNSTABLE_DELAY_SECONDS))
            previous_alarm_state = self.alarm_state
            decision = self._evaluate_decision_engine(observations, now, anonymous_inside,
                                                      frame_size=(width, height))
            self.alarm_person_ids = sorted(int(v["track_id"]) for v in decision.tracks.values()
                                           if v.get("state") == "ALARM" and v.get("track_id") is not None)
            self.warning_person_ids = sorted(int(v["track_id"]) for v in decision.tracks.values()
                                             if v.get("state") == "WARNING" and v.get("track_id") is not None)
            self.review_person_ids = sorted(int(v["track_id"]) for v in decision.tracks.values()
                                            if v.get("state") == "REVIEW" and v.get("track_id") is not None)
            decision_by_id = {str(k): v.get("state") for k, v in decision.tracks.items()}
            spatial_tracks: dict[str, dict[str, Any]] = {}
            mapping_status = self._homography.status((width, height))
            for det in detections:
                if det.get("id") is not None:
                    det["decision_state"] = decision_by_id.get(str(det["id"]), "UNKNOWN")
                    x1, y1, x2, y2 = det["box"]
                    foot_pixel = [float(np.clip((x1 + x2) / 2.0, 0, width - 1)),
                                  float(np.clip(y2, 0, height - 1))]
                    floor_xy = self._homography.transform(foot_pixel, (width, height))
                    spatial_tracks[str(int(det["id"]))] = {
                        "camera_id": mapping_status.get("camera_id", "usb_external"),
                        "calibration_id": mapping_status.get("calibration_id"),
                        "track_id": int(det["id"]), "foot_pixel": foot_pixel,
                        "floor_xy": list(floor_xy) if floor_xy is not None else None,
                        "mapping_valid": floor_xy is not None and bool(mapping_status.get("valid")),
                        "mapping_reason": mapping_status.get("reason"),
                        "observed_at": datetime.now(BUSINESS_TZ).isoformat(timespec="milliseconds"),
                        "decision_state": det["decision_state"]}
                else:
                    det["decision_state"] = "ANONYMOUS"
            self._spatial_tracks = spatial_tracks
            alarm = self.alarm_state == "ALARM"
            for item in decision.events:
                event_type = str(item.get("type") or "decision_event")
                if event_type == "alarm_state_changed":
                    self._emit(event_type, -1, f"Trạng thái an ninh: {item.get('state')}.",
                               severity=item.get("severity", "info"), alarm_state=item.get("state"), zone_period=period,
                               reason="health_fault" if health_fault else None,
                               health_reason=self._health_reason if health_fault else None)
                elif event_type in {"unauthorized_entry", "wrong_zone", "anonymous_zone_alarm"}:
                    self._emit(event_type, int(item.get("track_id", -1)),
                               f"Track {item.get('track_id')} không có quyền vào vùng {item.get('zone')}.",
                               severity="critical", authorized=False, zone=item.get("zone"))
                elif event_type in {"access_pending", "zone_warning"}:
                    self._emit(event_type, int(item.get("track_id", -1)),
                               f"Track {item.get('track_id')} đang ở trạng thái {item.get('state')}.",
                               severity="warning", zone=item.get("zone"), reason=item.get("reason"))
                elif event_type == "review_required":
                    self._emit(event_type, int(item.get("track_id", -1)),
                               f"Track {item.get('track_id')} cần được kiểm tra.",
                               severity="medium", zone=item.get("zone"), reason=item.get("reason"))
            self._apply_events(entered, exited, now)
            self._zone_warning = zone_aspect_warning(zone_size, (width, height))

        # Cập nhật overlay riêng; luồng render lấy trạng thái mới nhất và vẽ lên frame camera mới nhất.
        display_detections = [dict(item) for item in detections]
        with self._lock:
            self._display_state = (display_detections, poly_i.copy(), alarm, set(authorized))
            self._display_state_at = time.monotonic()
            new_event_exists = any(str(event.get("event_id")) not in event_ids_before for event in self._events)
        # Chỉ mã hóa thêm ảnh ở nhánh AI khi thực sự cần lưu bằng chứng sự kiện.
        if new_event_exists:
            evidence_jpeg = self._render(frame.copy(), detections, poly_i, alarm, authorized, quality=82)
            self._attach_evidence(evidence_jpeg, event_ids_before)
        return None

    def _render(self, canvas: np.ndarray, detections: list[dict[str, Any]], poly_i: np.ndarray,
                alarm: bool, authorized: set[int], quality: int = 80) -> bytes | None:
        height, width = canvas.shape[:2]
        zone_color = RED if alarm else YELLOW
        if alarm:  # tô đỏ mờ cả vùng cho dễ thấy
            overlay = canvas.copy()
            cv2.fillPoly(overlay, [poly_i.reshape(-1, 1, 2)], RED)
            cv2.addWeighted(overlay, 0.22, canvas, 0.78, 0, canvas)
        cv2.polylines(canvas, [poly_i.reshape(-1, 1, 2)], True, zone_color, 3 if alarm else 2)
        label_pos = (int(poly_i[0][0]), max(20, int(poly_i[0][1]) - 8))
        cv2.putText(canvas, "ALARM: NGUOI TRONG VUNG NGUY HIEM" if alarm else "KHOAI MONITOR ZONE",
                    label_pos, cv2.FONT_HERSHEY_SIMPLEX, 0.55, zone_color, 2, cv2.LINE_AA)
        for det in detections:
            x1, y1, x2, y2 = (int(v) for v in det["box"])
            decision_state = str(det.get("decision_state", "UNKNOWN"))
            color = RED if decision_state == "ALARM" else YELLOW if decision_state in {"WARNING", "REVIEW", "ANONYMOUS"} else GREEN
            tid = det["id"]
            label = f"ID {tid} | {det['conf']:.2f}" if tid is not None else f"person | {det['conf']:.2f}"
            if decision_state == "AUTHORIZED" and tid in authorized:
                label += " | CARD OK"
            elif decision_state == "REVIEW":
                label += " | CAN XEM LAI"
            elif decision_state in {"WARNING", "ALARM", "ANONYMOUS"}:
                label += f" | {decision_state}"
            cv2.rectangle(canvas, (x1, y1), (x2, y2), color, 2)
            foot = (round((x1 + x2) / 2), min(height - 1, y2))
            cv2.circle(canvas, foot, 5, RED if det["raw_inside"] else GREEN, -1)
            cv2.putText(canvas, label, (x1, max(20, y1 - 7)), cv2.FONT_HERSHEY_SIMPLEX, 0.48, color, 2, cv2.LINE_AA)
        if self._model is None:
            note = "AI DANG TAI MODEL..." if self._model_loading else "AI CHUA SAN SANG (xem log / model_error)"
            cv2.putText(canvas, note, (10, height - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.5, YELLOW, 2, cv2.LINE_AA)
        ok, jpeg = cv2.imencode(".jpg", canvas, [int(cv2.IMWRITE_JPEG_QUALITY), int(quality)])
        return jpeg.tobytes() if ok else None


detector = CameraDetector()
