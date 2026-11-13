"""Optional WebRTC output consuming the detector's already-rendered JPEG frames.

Install aiortc from requirements-webrtc.txt to enable this experimental endpoint.
MJPEG remains the stable fallback and continues to use the same detector worker.
"""
from __future__ import annotations

import asyncio
import threading
import time


def create_peer_connection(detector, stream_manager=None):
    try:
        from aiortc import RTCPeerConnection, RTCSessionDescription, VideoStreamTrack
        from av import VideoFrame
        import cv2
        import numpy as np
    except ImportError as exc:
        raise RuntimeError("WebRTC chưa được cài. Cài requirements-webrtc.txt để bật luồng thử nghiệm.") from exc

    class SharedJpegTrack(VideoStreamTrack):
        """Decode the latest annotated JPEG; never starts a second YOLO inference loop."""
        def __init__(self):
            super().__init__()
            self._last_jpeg = None
            self._last_source_jpeg = None
            self._last_frame: np.ndarray = np.zeros((480, 640, 3), dtype=np.uint8)
            self._last_at = 0.0

        async def recv(self):
            pts, time_base = await self.next_timestamp()
            jpeg = await asyncio.to_thread(detector.latest_jpeg)
            if jpeg and jpeg != self._last_source_jpeg:
                if stream_manager is not None:
                    # WebRTC's encoded network byte count is not available here;
                    # count distinct source frames only, not repeated recv() calls.
                    stream_manager.record_frame("usb", 0)
                self._last_source_jpeg = jpeg
                self._last_jpeg = jpeg
                self._last_at = time.monotonic()
                raw = np.frombuffer(jpeg, dtype=np.uint8)
                decoded = cv2.imdecode(raw, cv2.IMREAD_COLOR)
                if decoded is not None:
                    self._last_frame = cv2.cvtColor(decoded, cv2.COLOR_BGR2RGB)
            frame = VideoFrame.from_ndarray(self._last_frame, format="rgb24")
            frame.pts = pts
            frame.time_base = time_base
            return frame

    pc = RTCPeerConnection()
    pc.addTrack(SharedJpegTrack())
    return pc, RTCSessionDescription
