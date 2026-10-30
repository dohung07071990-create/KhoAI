"""YOLOv8 + ByteTrack person detection and intrusion-zone alerts for KhoAI."""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence
from zoneinfo import ZoneInfo

import cv2
import numpy as np

logger = logging.getLogger(__name__)
AI_DIR = Path(__file__).resolve().parent
ZONE_FILE = Path(os.getenv("KHOAI_ZONE_FILE", str(AI_DIR / "zone.json")))
BUSINESS_TZ = ZoneInfo(os.getenv("BUSINESS_TIMEZONE", "Asia/Ho_Chi_Minh"))
DEFAULT_ZONE: tuple[tuple[float, float], ...] = (
    (0.20, 0.40), (0.80, 0.40), (0.95, 0.95), (0.05, 0.95),
)
ALERT_INTERVAL_SECONDS = 3.0
MAX_EVENTS = 100


def load_zone_file() -> tuple[tuple[float, float], ...]:
    """Load normalized polygon points from ai/zone.json; use safe default if absent."""
    if not ZONE_FILE.is_file():
        return DEFAULT_ZONE
    try:
        data = json.loads(ZONE_FILE.read_text(encoding="utf-8"))
        points = data.get("points", data) if isinstance(data, dict) else data
        zone = tuple((float(p[0]), float(p[1])) for p in points)
        validate_zone(zone)
        return zone
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        logger.warning("Cannot read zone file %s (%s); using default zone", ZONE_FILE, exc)
        return DEFAULT_ZONE


def validate_zone(zone: Sequence[tuple[float, float]]) -> None:
    if len(zone) < 3:
        raise ValueError("Vùng giám sát cần ít nhất 3 điểm.")
    if any(not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0) for x, y in zone):
        raise ValueError("Tọa độ vùng phải nằm trong khoảng 0–1.")


class CameraDetector:
    """One camera owner; YOLO detections are tracked persistently by ByteTrack."""
    def __init__(self, camera_index: int | None = None,
                 zone: Sequence[tuple[float, float]] | None = None) -> None:
        if camera_index is None:
            try:
                camera_index = int(os.getenv("CAMERA_INDEX", "0"))
            except ValueError:
                logger.warning("Invalid CAMERA_INDEX; using camera 0")
                camera_index = 0
        self.camera_index = camera_index
        self.zone = tuple((float(x), float(y)) for x, y in (zone or load_zone_file()))
        validate_zone(self.zone)
        self._lock = threading.RLock()
        self._capture: cv2.VideoCapture | None = None
        self._model: Any | None = None
        self._model_attempted = False
        self._last_camera_log = float("-inf")
        self._last_alert = float("-inf")
        self._previous_inside_ids: set[int] = set()
        self._events: deque[dict[str, Any]] = deque(maxlen=MAX_EVENTS)
        self.person_in_zone = False
        self.camera_available = False
        self.tracked_person_ids: list[int] = []
        self.last_event: dict[str, Any] | None = None

    def set_zone(self, points: Sequence[tuple[float, float]], save: bool = True) -> None:
        zone = tuple((float(x), float(y)) for x, y in points)
        validate_zone(zone)
        with self._lock:
            self.zone = zone
            self._previous_inside_ids.clear()
            if save:
                ZONE_FILE.parent.mkdir(parents=True, exist_ok=True)
                ZONE_FILE.write_text(
                    json.dumps({"points": [list(p) for p in zone]}, indent=2), encoding="utf-8"
                )

    def get_events(self, limit: int = 30) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._events)[:max(1, min(limit, MAX_EVENTS))]

    def _ensure_camera(self) -> bool:
        if self._capture is not None and self._capture.isOpened():
            return True
        if self._capture is not None:
            self._capture.release()
            self._capture = None
        try:
            capture = cv2.VideoCapture(self.camera_index)
            if capture.isOpened():
                self._capture = capture
                return True
            capture.release()
        except Exception:
            logger.exception("Could not open camera index %s", self.camera_index)
        now = time.monotonic()
        if now - self._last_camera_log >= ALERT_INTERVAL_SECONDS:
            logger.warning("Camera %s unavailable; check CAMERA_INDEX and connection", self.camera_index)
            self._last_camera_log = now
        return False

    def _ensure_model(self) -> bool:
        if self._model is not None:
            return True
        if self._model_attempted:
            return False
        self._model_attempted = True
        try:
            from ultralytics import YOLO
            weights = os.getenv("KHOAI_YOLO_MODEL", "yolov8n.pt")
            self._model = YOLO(weights)
            logger.info("Loaded YOLO model %s; ByteTrack enabled", weights)
            return True
        except Exception:
            logger.exception("Could not load YOLO model")
            return False

    def _zone_pixels(self, width: int, height: int) -> list[tuple[int, int]]:
        return [(round(x * (width - 1)), round(y * (height - 1))) for x, y in self.zone]

    def read_jpeg(self) -> bytes | None:
        """Return annotated JPEG; returns None if camera/model/frame is unavailable."""
        with self._lock:
            if not self._ensure_camera() or not self._ensure_model():
                self.person_in_zone = False
                self.camera_available = False
                self.tracked_person_ids = []
                return None
            assert self._capture is not None and self._model is not None
            ok, frame = self._capture.read()
            if not ok or frame is None:
                self._capture.release()
                self._capture = None
                self.person_in_zone = False
                self.camera_available = False
                self.tracked_person_ids = []
                return None
            try:
                self.camera_available = True
                height, width = frame.shape[:2]
                polygon = self._zone_pixels(width, height)
                polygon_array = np.asarray(polygon, dtype=np.int32)
                cv2.polylines(frame, [polygon_array], True, (0, 220, 255), 2)
                cv2.putText(frame, "INTRUSION ZONE", (polygon[0][0], max(20, polygon[0][1] - 8)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 220, 255), 2, cv2.LINE_AA)

                results = self._model.track(
                    source=frame, persist=True, tracker="bytetrack.yaml", classes=[0],
                    device=os.getenv("KHOAI_AI_DEVICE", "cpu"), conf=0.35, verbose=False,
                )
                current_ids: list[int] = []
                inside_ids: set[int] = set()
                any_inside = False
                if results:
                    boxes = results[0].boxes
                    if boxes is not None:
                        ids_obj = boxes.id
                        for idx, box in enumerate(boxes):
                            if int(box.cls[0].item()) != 0:
                                continue
                            x1, y1, x2, y2 = (int(v) for v in box.xyxy[0].tolist())
                            confidence = float(box.conf[0].item())
                            track_id = int(ids_obj[idx].item()) if ids_obj is not None else None
                            footpoint = (round((x1 + x2) / 2), y2)
                            inside = cv2.pointPolygonTest(polygon_array, (float(footpoint[0]), float(footpoint[1])), False) >= 0
                            color = (0, 0, 255) if inside else (40, 220, 40)
                            if track_id is not None:
                                current_ids.append(track_id)
                                if inside:
                                    inside_ids.add(track_id)
                            any_inside = any_inside or inside
                            label = f"ID {track_id} | {confidence:.2f}" if track_id is not None else f"person | {confidence:.2f}"
                            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                            cv2.circle(frame, footpoint, 4, color, -1)
                            cv2.putText(frame, label, (x1, max(20, y1 - 7)), cv2.FONT_HERSHEY_SIMPLEX,
                                        0.55, color, 2, cv2.LINE_AA)

                # Emit an event only when a tracked person newly enters the restricted zone.
                new_entries = inside_ids - self._previous_inside_ids
                now = time.monotonic()
                if new_entries and now - self._last_alert >= ALERT_INTERVAL_SECONDS:
                    for track_id in sorted(new_entries):
                        event = {
                            "event_at": datetime.now(BUSINESS_TZ).isoformat(timespec="seconds"),
                            "type": "intrusion", "track_id": track_id,
                            "message": f"Phát hiện người ID {track_id} đi vào vùng cấm",
                        }
                        self._events.appendleft(event)
                        self.last_event = event
                        logger.warning(event["message"])
                    self._last_alert = now
                self._previous_inside_ids = inside_ids
                self.tracked_person_ids = sorted(set(current_ids))
                self.person_in_zone = any_inside
                encoded, jpeg = cv2.imencode(".jpg", frame)
                return jpeg.tobytes() if encoded else None
            except Exception:
                self.person_in_zone = False
                self.camera_available = False
                logger.exception("Person tracking/inference/frame encoding failed")
                return None

    def close(self) -> None:
        with self._lock:
            if self._capture is not None:
                self._capture.release()
                self._capture = None
            self.camera_available = False
            self.person_in_zone = False
            self.tracked_person_ids = []
            self._previous_inside_ids.clear()


detector = CameraDetector()
