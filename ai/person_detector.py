"""KhoAI vision pipeline: camera USB -> YOLO person + ByteTrack -> luật vùng cấm.

Viết lại (v0.3.0). Những lỗi gốc đã sửa:

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
  * Báo đỏ "chớp tắt" vì bounding box rung: thêm trễ (hysteresis) vào/ra theo số frame.
  * Box nhỏ vô lý (ghế, bóng, vật thể bị nhận nhầm là người) bị lọc theo chiều cao tối thiểu.
  * draw_zone.py vẽ ở độ phân giải gốc của camera còn detector ép 640x480 -> lệch khung nhìn.
    Giờ dùng chung một hàm mở camera và lưu kèm kích thước khung (frame_size) để cảnh báo khi lệch.
  * File zone.json được nạp lại tự động khi thay đổi (bản cũ chỉ đọc lúc khởi động).

Track ID là ID theo dõi tạm thời, không phải danh tính. Gắn thẻ <-> người phải do người vận hành xác nhận.
"""
from __future__ import annotations

import json
import logging
import os
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
    try:
        return max(minimum, float(os.getenv(name, str(default))))
    except ValueError:
        return default


def _env_int(name: str, default: int, minimum: int = 0) -> int:
    return int(_env_float(name, default, minimum))


HEATMAP_HALF_LIFE_SECONDS = _env_float("KHOAI_HEATMAP_HALF_LIFE", 45.0, 5.0)
MAX_EVIDENCE_FILES = _env_int("KHOAI_CAMERA_EVIDENCE_MAX_FILES", 500, 50)


DWELL_SECONDS = _env_float("KHOAI_DWELL_SECONDS", 30.0, 1.0)
CONFIDENCE = min(0.95, max(0.1, _env_float("KHOAI_CONFIDENCE", 0.35)))
IMAGE_SIZE = _env_int("KHOAI_IMAGE_SIZE", 640, 320)
FRAME_WIDTH = _env_int("KHOAI_FRAME_WIDTH", 640, 320)
FRAME_HEIGHT = _env_int("KHOAI_FRAME_HEIGHT", 480, 240)
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
ENTER_FRAMES = _env_int("KHOAI_ENTER_FRAMES", 2, 1)    # số frame liên tiếp "ở trong" để xác nhận vào vùng
EXIT_FRAMES = _env_int("KHOAI_EXIT_FRAMES", 4, 1)      # số frame liên tiếp "ở ngoài" để xác nhận rời vùng
LOST_FRAMES = _env_int("KHOAI_LOST_FRAMES", 20, 1)     # track mất bao nhiêu frame thì coi như đã biến mất
MIN_BOX_HEIGHT_RATIO = _env_float("KHOAI_MIN_BOX_HEIGHT", 0.08)  # lọc box quá nhỏ (tỉ lệ chiều cao khung)
AUTH_TTL_SECONDS = _env_float("KHOAI_AUTH_TTL_SECONDS", 300.0, 5.0)
CAMERA_SCAN_MAX = _env_int("KHOAI_CAMERA_SCAN_MAX", 5, 0)

RED, GREEN, YELLOW = (0, 0, 255), (40, 220, 40), (0, 220, 255)


# --------------------------------------------------------------------------------------
# Vùng cấm: nạp / lưu / kiểm tra
# --------------------------------------------------------------------------------------
def validate_zone(zone: Sequence[tuple[float, float]]) -> None:
    if len(zone) < 3:
        raise ValueError("Vùng giám sát cần ít nhất 3 điểm.")
    if any(not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0) for x, y in zone):
        raise ValueError("Tọa độ vùng phải nằm trong khoảng 0–1.")
    area = 0.0
    for i, (x1, y1) in enumerate(zone):
        x2, y2 = zone[(i + 1) % len(zone)]
        area += x1 * y2 - x2 * y1
    if abs(area) / 2 < 0.002:
        raise ValueError("Vùng quá nhỏ hoặc các điểm thẳng hàng; hãy chọn lại các điểm.")


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


def zone_to_pixels(zone: Sequence[tuple[float, float]], width: int, height: int) -> np.ndarray:
    """Chuẩn hóa -> pixel (float32). Cùng công thức (w-1, h-1) với draw_zone.py."""
    return np.asarray([(x * (width - 1), y * (height - 1)) for x, y in zone], dtype=np.float32)


def _inside(poly: np.ndarray, x: float, y: float) -> bool:
    return cv2.pointPolygonTest(poly, (float(x), float(y)), False) >= 0


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
        self._raw_cond = threading.Condition()
        self._raw: np.ndarray | None = None
        self._raw_seq = 0
        self._last_raw_at = float("-inf")
        self._capture_last_tick = 0.0
        self._capture_fps = 0.0
        self._process_latency_ms = 0.0
        self._detection_count = 0
        self._out_cond = threading.Condition()
        self._out_jpeg: bytes | None = None
        self._out_seq = 0
        # ---- model ----
        self._model: Any | None = model
        self._model_error: str | None = None
        self._model_loading = False
        self._tracking_enabled = True
        # ---- trạng thái camera ----
        self._camera_info: OpenedCamera | None = None
        self._camera_error: str | None = None
        self._fps = 0.0
        # ---- trạng thái theo dõi ----
        self._track_state: dict[int, dict[str, int | bool]] = {}
        self._inside_since: dict[int, float] = {}
        self._authorized_tracks: dict[int, dict[str, Any]] = {}
        self._dwell_alerted: set[int] = set()
        self._events: deque[dict[str, Any]] = deque(maxlen=MAX_EVENTS)
        # Heatmap mật độ vị trí người, lưới thấp để nhẹ CPU/RAM; suy giảm theo thời gian.
        self._heatmap = np.zeros((HEATMAP_HEIGHT, HEATMAP_WIDTH), dtype=np.float32)
        self._heatmap_last_tick = time.monotonic()
        self.person_in_zone = False
        self.tracked_person_ids: list[int] = []
        self.last_event: dict[str, Any] | None = None
        self.last_frame_at: str | None = None
        self._zone_warning: str | None = None

    # ---------------------------------------------------------------- vòng đời
    def start(self) -> None:
        """Bắt đầu đọc camera + chạy AI ở nền. Gọi nhiều lần vẫn an toàn."""
        with self._life_lock:
            if any(t.is_alive() for t in self._threads):
                return
            self._stop.clear()
            self._threads = [
                threading.Thread(target=self._capture_loop, name="khoai-capture", daemon=True),
                threading.Thread(target=self._process_loop, name="khoai-ai", daemon=True),
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
            self._reset_tracking()
            self._authorized_tracks.clear()
        with self._raw_cond:
            self._raw = None
            self._last_raw_at = float("-inf")

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
    def _file_mtime() -> float | None:
        try:
            return ZONE_FILE.stat().st_mtime
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
            if zone != self.zone:
                self.zone = zone
                self._zone_frame_size = size
                self._reset_tracking()
                logger.info("Đã nạp lại vùng cấm từ %s", ZONE_FILE)

    def _zone_mask(self, width: int, height: int, zone: tuple, poly_i: np.ndarray) -> np.ndarray:
        key = (width, height, zone)
        if self._zone_mask_cache is None or self._zone_mask_cache[0] != key:
            mask = np.zeros((height, width), dtype=np.uint8)
            cv2.fillPoly(mask, [poly_i.reshape(-1, 1, 2)], 255)
            self._zone_mask_cache = (key, mask)
        return self._zone_mask_cache[1]

    # ---------------------------------------------------------------- liên kết thẻ & sự kiện
    def associate_card(self, track_id: int, uid: str, name: str | None = None) -> dict[str, Any]:
        """Liên kết tường minh một thẻ hợp lệ với ID đang hiển thị trên camera."""
        with self._lock:
            self._authorized_tracks[int(track_id)] = {"uid": uid, "name": name, "at": time.monotonic()}
            self._dwell_alerted.discard(int(track_id))
            return {"track_id": int(track_id), "uid": uid, "name": name, "associated": True}

    def revoke_track(self, track_id: int) -> None:
        with self._lock:
            self._authorized_tracks.pop(int(track_id), None)

    def get_events(self, limit: int = 30) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(event) for event in list(self._events)[:max(1, min(limit, MAX_EVENTS))]]

    def _emit(self, event_type: str, track_id: int, message: str, **extra: Any) -> None:
        event = {"event_id": uuid.uuid4().hex,
                 "event_at": datetime.now(BUSINESS_TZ).isoformat(timespec="seconds"),
                 "type": event_type, "track_id": track_id, "message": message,
                 "evidence_url": None, **extra}
        self._events.appendleft(event)
        self.last_event = event
        logger.warning("KhoAI event: %s", event)

    def _attach_evidence(self, jpeg: bytes | None, event_ids_before: set[str]) -> None:
        """Lưu JPEG đã vẽ box/vùng cho sự kiện mới; lỗi lưu ảnh không dừng pipeline AI."""
        if not jpeg:
            return
        with self._lock:
            pending = [event for event in self._events
                       if event.get("event_id") not in event_ids_before and not event.get("evidence_url")]
        for event in pending:
            event_id = str(event.get("event_id", ""))
            if not event_id or not all(ch in "0123456789abcdef" for ch in event_id):
                continue
            try:
                EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
                destination = EVIDENCE_DIR / f"{event_id}.jpg"
                temporary = destination.with_suffix(".jpg.tmp")
                temporary.write_bytes(jpeg)
                temporary.replace(destination)
                # Giới hạn dung lượng bằng cách giữ lại tối đa N ảnh mới nhất.
                files = sorted(EVIDENCE_DIR.glob("*.jpg"), key=lambda item: item.stat().st_mtime, reverse=True)
                for old_file in files[MAX_EVIDENCE_FILES:]:
                    try:
                        old_file.unlink(missing_ok=True)
                    except OSError:
                        logger.debug("Không xóa được ảnh bằng chứng cũ %s", old_file, exc_info=True)
                with self._lock:
                    event["evidence_url"] = f"/api/camera/evidence/{event_id}.jpg"
            except OSError:
                logger.warning("Không lưu được ảnh bằng chứng cho event %s", event_id, exc_info=True)

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
            available = (time.monotonic() - self._last_raw_at) < 3.0
            return {
                "running": self.running,
                "camera_available": available,
                "camera_source": info.describe() if info else str(self._source_spec),
                "camera_error": None if available else self._camera_error,
                "frame_size": [info.width, info.height] if info else None,
                "fps": round(self._fps, 1),  # tương thích dashboard cũ: FPS AI
                "process_fps": round(self._fps, 1),
                "capture_fps": round(self._capture_fps, 1),
                "process_latency_ms": round(self._process_latency_ms, 1),
                "frame_age_ms": round(max(0.0, time.monotonic() - self._last_raw_at) * 1000, 1)
                    if self._last_raw_at > 0 else None,
                "detections": self._detection_count,
                "zone_points": [[x, y] for x, y in self.zone],
                "zone_frame_size": list(self._zone_frame_size) if self._zone_frame_size else None,
                "model_loaded": self._model is not None,
                "model_loading": self._model_loading,
                "model_error": self._model_error,
                "tracking": self._tracking_enabled,
                "zone_mode": ZONE_MODE,
                "zone_warning": self._zone_warning,
                "person_in_zone": self.person_in_zone,
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
                        with self._lock:
                            self._camera_info = None
                            self._camera_error = (
                                f"Không mở được camera (CAMERA_INDEX={self._source_spec}). Chạy "
                                "`python -m ai.list_cameras` để tìm index đúng, đóng app khác đang dùng camera, "
                                "hoặc thử cổng USB khác.")
                        logger.warning("%s", self._camera_error)
                        self._stop.wait(backoff)
                        backoff = min(10.0, backoff * 1.7)
                        continue
                    backoff, failures = 1.0, 0
                    with self._lock:
                        self._camera_info, self._camera_error = cap, None
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
                            self._camera_error = "Mất tín hiệu camera, đang thử kết nối lại..."
                    else:
                        time.sleep(0.03)
                    continue
                failures = 0
                self._publish_raw(frame)
        except Exception:  # noqa: BLE001
            logger.exception("Luồng đọc camera bị lỗi")
            with self._lock:
                self._camera_error = "Luồng đọc camera bị lỗi; xem log server."
        finally:
            if cap is not None:
                cap.capture.release()

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
        while not self._stop.is_set():
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
            except Exception:  # noqa: BLE001
                logger.exception("Lỗi khi xử lý frame (AI/vẽ/mã hóa)")
                jpeg = None
            if jpeg is not None:
                with self._out_cond:
                    self._out_jpeg = jpeg
                    self._out_seq += 1
                    self._out_cond.notify_all()
            tick = time.monotonic()
            fps_ema = 0.9 * fps_ema + 0.1 / max(1e-3, tick - last_tick) if fps_ema else 1.0 / max(1e-3, tick - last_tick)
            self._fps, last_tick = fps_ema, tick
            with self._lock:
                self._process_latency_ms = max(0.0, tick - frame_captured_at) * 1000.0

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

    def _update_tracks(self, detections: list[dict[str, Any]], now: float) -> tuple[list[int], list[int]]:
        """Hysteresis theo track: vào sau ENTER_FRAMES frame liên tiếp, ra sau EXIT_FRAMES frame liên tiếp."""
        entered: list[int] = []
        exited: list[int] = []
        seen: set[int] = set()
        for det in detections:
            tid = det["id"]
            if tid is None:                       # chưa có ID: vẫn tính là "trong vùng" ngay theo frame
                det["inside"] = det["raw_inside"]
                continue
            seen.add(tid)
            st = self._track_state.setdefault(tid, {"in": 0, "out": 0, "inside": False, "missing": 0})
            st["missing"] = 0
            if det["raw_inside"]:
                st["in"], st["out"] = int(st["in"]) + 1, 0
            else:
                st["in"], st["out"] = 0, int(st["out"]) + 1
            if not st["inside"] and int(st["in"]) >= ENTER_FRAMES:
                st["inside"] = True
                entered.append(tid)
            elif st["inside"] and int(st["out"]) >= EXIT_FRAMES:
                st["inside"] = False
                exited.append(tid)
            det["inside"] = bool(st["inside"])
        for tid in list(self._track_state):
            if tid in seen:
                continue
            st = self._track_state[tid]
            st["missing"] = int(st["missing"]) + 1
            if int(st["missing"]) > LOST_FRAMES:
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
            if auth:
                self._emit("zone_entry", tid, f"Người ID {tid} đi vào vùng bảo vệ (đã liên kết thẻ).",
                           severity="low", authorized=True, card_uid=auth.get("uid"))
            else:
                self._emit("unauthorized_entry", tid,
                           f"Người ID {tid} vào vùng nhưng chưa liên kết thẻ hợp lệ.", severity="high", authorized=False)
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
            self._authorized_tracks.pop(tid, None)
        for tid, auth in list(self._authorized_tracks.items()):  # thẻ liên kết quá hạn thì thu hồi
            if now - float(auth.get("at", now)) > AUTH_TTL_SECONDS:
                self._authorized_tracks.pop(tid, None)

    def _process_frame(self, frame: np.ndarray) -> bytes | None:
        now = time.monotonic()
        self._maybe_reload_zone(now)
        height, width = frame.shape[:2]
        with self._lock:
            zone, zone_size = self.zone, self._zone_frame_size
        poly = zone_to_pixels(zone, width, height)
        poly_i = np.round(poly).astype(np.int32)

        # AI nhìn frame SẠCH (bản cũ vẽ vùng lên frame rồi mới đưa cho YOLO).
        detections = self._detect(frame)
        detections = [d for d in detections
                      if (d["box"][3] - d["box"][1]) / height >= MIN_BOX_HEIGHT_RATIO]
        with self._lock:
            self._detection_count = len(detections)
        mask = self._zone_mask(width, height, zone, poly_i) if ZONE_MODE == "overlap" else None
        for det in detections:
            det["raw_inside"] = is_box_in_zone(det["box"], (width, height), poly, ZONE_MODE, mask,
                                               ZONE_OVERLAP_MIN, TRUNCATED_FALLBACK)

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
            entered, exited = self._update_tracks(detections, now)
            self._apply_events(entered, exited, now)
            self.person_in_zone = any(d["inside"] for d in detections)
            self.tracked_person_ids = sorted({d["id"] for d in detections if d["id"] is not None})
            self.last_frame_at = datetime.now(BUSINESS_TZ).isoformat(timespec="seconds")
            authorized = set(self._authorized_tracks)
            alarm = self.person_in_zone
            self._zone_warning = None
            if zone_size and zone_size[1] and abs(zone_size[0] / zone_size[1] - width / height) / (width / height) > 0.03:
                self._zone_warning = (f"Vùng được vẽ ở khung {zone_size[0]}x{zone_size[1]} nhưng camera đang là "
                                      f"{width}x{height} (khác tỉ lệ) -> vùng có thể lệch. Hãy vẽ lại vùng bảo vệ.")

        jpeg = self._render(frame.copy(), detections, poly_i, alarm, authorized)
        self._attach_evidence(jpeg, event_ids_before)
        return jpeg

    def _render(self, canvas: np.ndarray, detections: list[dict[str, Any]], poly_i: np.ndarray,
                alarm: bool, authorized: set[int]) -> bytes | None:
        height, width = canvas.shape[:2]
        zone_color = RED if alarm else YELLOW
        if alarm:  # tô đỏ mờ cả vùng cho dễ thấy
            overlay = canvas.copy()
            cv2.fillPoly(overlay, [poly_i.reshape(-1, 1, 2)], RED)
            cv2.addWeighted(overlay, 0.22, canvas, 0.78, 0, canvas)
        cv2.polylines(canvas, [poly_i.reshape(-1, 1, 2)], True, zone_color, 3 if alarm else 2)
        label_pos = (int(poly_i[0][0]), max(20, int(poly_i[0][1]) - 8))
        cv2.putText(canvas, "CANH BAO: CO NGUOI TRONG VUNG CAM" if alarm else "KHOAI MONITOR ZONE",
                    label_pos, cv2.FONT_HERSHEY_SIMPLEX, 0.55, zone_color, 2, cv2.LINE_AA)
        for det in detections:
            x1, y1, x2, y2 = (int(v) for v in det["box"])
            color = RED if det["inside"] else GREEN
            tid = det["id"]
            label = f"ID {tid} | {det['conf']:.2f}" if tid is not None else f"person | {det['conf']:.2f}"
            if tid in authorized:
                label += " | CARD OK"
            cv2.rectangle(canvas, (x1, y1), (x2, y2), color, 2)
            foot = (round((x1 + x2) / 2), min(height - 1, y2))
            cv2.circle(canvas, foot, 5, RED if det["raw_inside"] else GREEN, -1)
            cv2.putText(canvas, label, (x1, max(20, y1 - 7)), cv2.FONT_HERSHEY_SIMPLEX, 0.48, color, 2, cv2.LINE_AA)
        if self._model is None:
            note = "AI DANG TAI MODEL..." if self._model_loading else "AI CHUA SAN SANG (xem log / model_error)"
            cv2.putText(canvas, note, (10, height - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.5, YELLOW, 2, cv2.LINE_AA)
        ok, jpeg = cv2.imencode(".jpg", canvas, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
        return jpeg.tobytes() if ok else None


detector = CameraDetector()
