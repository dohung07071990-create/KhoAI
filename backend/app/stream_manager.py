"""Lightweight viewer/session accounting for camera stream distribution.

This manager controls only outbound delivery. It deliberately never starts or stops
camera capture, YOLO inference, ByteTrack, or the security decision engine.
"""
from __future__ import annotations

import threading
import time
import uuid
from collections import defaultdict
from typing import Any


class StreamManager:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._sessions: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
        self._metrics: dict[str, dict[str, Any]] = defaultdict(self._new_metrics)

    @staticmethod
    def _new_metrics() -> dict[str, Any]:
        return {
            "connections_total": 0,
            "disconnects_total": 0,
            "frames_sent": 0,
            "bytes_sent": 0,
            "last_frame_at": None,
            "last_frame_age_ms": None,
            "last_frame_latency_ms": None,
        }

    def connect(self, stream: str, protocol: str) -> str:
        if not stream or protocol not in {"mjpeg", "webrtc", "websocket"}:
            raise ValueError("Invalid stream or protocol")
        session_id = uuid.uuid4().hex
        now = time.time()
        with self._lock:
            self._sessions[stream][session_id] = {"protocol": protocol, "connected_at": now}
            self._metrics[stream]["connections_total"] += 1
        return session_id

    def disconnect(self, stream: str, session_id: str) -> bool:
        with self._lock:
            removed = self._sessions.get(stream, {}).pop(session_id, None)
            if removed is not None:
                self._metrics[stream]["disconnects_total"] += 1
                return True
            return False

    def record_frame(self, stream: str, byte_count: int, *, frame_age_ms: float | None = None,
                     latency_ms: float | None = None) -> None:
        with self._lock:
            metric = self._metrics[stream]
            metric["frames_sent"] += 1
            metric["bytes_sent"] += max(0, int(byte_count))
            metric["last_frame_at"] = time.time()
            metric["last_frame_age_ms"] = round(frame_age_ms, 2) if frame_age_ms is not None else None
            metric["last_frame_latency_ms"] = round(latency_ms, 2) if latency_ms is not None else None

    def record_bytes(self, stream: str, byte_count: int) -> None:
        """Record transport bytes when the protocol does not expose frame boundaries."""
        with self._lock:
            self._metrics[stream]["bytes_sent"] += max(0, int(byte_count))

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            streams: dict[str, Any] = {}
            for stream in sorted(set(self._sessions) | set(self._metrics)):
                sessions = list(self._sessions.get(stream, {}).values())
                by_protocol: dict[str, int] = defaultdict(int)
                for session in sessions:
                    by_protocol[session["protocol"]] += 1
                metrics = dict(self._metrics[stream])
                streams[stream] = {
                    "viewers": len(sessions),
                    "active": bool(sessions),
                    "protocols": dict(by_protocol),
                    **metrics,
                }
            return {"ok": True, "distribution": "on_demand", "streams": streams,
                    "capture_policy": "independent", "ai_policy": "always_independent"}


stream_manager = StreamManager()
