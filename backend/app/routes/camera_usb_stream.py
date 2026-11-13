"""USB camera MJPEG stream endpoint."""
from __future__ import annotations
import asyncio
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse


def create_usb_camera_stream_router(services: Any) -> tuple[APIRouter, Any]:
    router = APIRouter()

    @router.get('/api/camera/stream', dependencies=[Depends(services.require_admin_query)])
    def camera_stream(request: Request) -> StreamingResponse:
        """MJPEG stream annotated by the USB-camera detector."""
        session_digest = getattr(request.state, "khoai_session_digest", None)
        try:
            detector = services.detector_provider()
            services.ensure_camera_for_read(request, detector)
        except HTTPException:
            raise
        except Exception as exc:
            services.logger.exception("Không thể khởi động luồng camera")
            raise HTTPException(status_code=503, detail="Không thể khởi động luồng camera lúc này.") from exc

        async def frames():
            manager = services.stream_manager_provider()
            session_id = manager.connect("usb", "mjpeg")
            last_seq = 0
            try:
                while True:
                    if not await services.session_digest_valid(session_digest):
                        break
                    result = await asyncio.to_thread(detector.wait_for_frame, last_seq, timeout=2.0)
                    if result is None:
                        if not detector.running:
                            break
                        continue
                    last_seq, jpeg = result
                    payload = (b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
                               + str(len(jpeg)).encode("ascii") + b"\r\n\r\n" + jpeg + b"\r\n")
                    yield payload
                    manager.record_frame("usb", len(jpeg))
            except asyncio.CancelledError:
                raise
            finally:
                manager.disconnect("usb", session_id)

        return StreamingResponse(frames(), media_type="multipart/x-mixed-replace; boundary=frame",
            headers={"Cache-Control": "no-cache, no-store, must-revalidate", "Pragma": "no-cache", "X-Accel-Buffering": "no"})

    return router, camera_stream
