"""Authenticated ESP32-CAM MJPEG proxy endpoint."""
from __future__ import annotations
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask


def create_inside_camera_stream_router(services: Any) -> tuple[APIRouter, Any]:
    router = APIRouter()

    @router.get('/api/camera/inside/stream', dependencies=[Depends(services.require_admin_query)])
    async def inside_camera_stream(request: Request) -> StreamingResponse:
        """Authenticated backend proxy for the ESP32-CAM MJPEG stream."""
        upstream_url = services.environment("KHOAI_ESP32_CAM_STREAM_URL", "").strip()
        if not upstream_url:
            raise HTTPException(status_code=503, detail="Chưa cấu hình KHOAI_ESP32_CAM_STREAM_URL trong backend.")
        if not upstream_url.startswith(("http://", "https://")):
            raise HTTPException(status_code=503, detail="KHOAI_ESP32_CAM_STREAM_URL phải là HTTP(S) URL hợp lệ.")
        try:
            import httpx
            client = httpx.AsyncClient(timeout=httpx.Timeout(connect=5.0, read=15.0, write=5.0, pool=5.0), follow_redirects=False)
            upstream_request = client.build_request("GET", upstream_url)
            upstream = await client.send(upstream_request, stream=True)
            if upstream.status_code < 200 or upstream.status_code >= 300:
                try:
                    await upstream.aclose()
                finally:
                    await client.aclose()
                raise HTTPException(status_code=502, detail=f"ESP32-CAM trả HTTP {upstream.status_code}.")
            content_type = upstream.headers.get("content-type", "multipart/x-mixed-replace; boundary=frame")
            manager = services.stream_manager_provider()
            lifecycle = {"session_id": None, "closed": False}
            session_digest = getattr(request.state, "khoai_session_digest", None)

            async def cleanup() -> None:
                if lifecycle["closed"]:
                    return
                lifecycle["closed"] = True
                if lifecycle["session_id"] is not None:
                    manager.disconnect("inside", lifecycle["session_id"])
                    lifecycle["session_id"] = None
                try:
                    await upstream.aclose()
                finally:
                    await client.aclose()

            async def body():
                lifecycle["session_id"] = manager.connect("inside", "mjpeg")
                try:
                    async for chunk in upstream.aiter_raw():
                        if not await services.session_digest_valid(session_digest):
                            break
                        yield chunk
                        manager.record_bytes("inside", len(chunk))
                finally:
                    await cleanup()

            return StreamingResponse(body(), headers={"Content-Type": content_type,
                "Cache-Control": "no-store", "X-Accel-Buffering": "no"}, background=BackgroundTask(cleanup))
        except HTTPException:
            raise
        except Exception as exc:
            services.logger.exception("ESP32-CAM proxy failed")
            raise HTTPException(status_code=502, detail="Không thể kết nối ESP32-CAM lúc này.") from exc

    return router, inside_camera_stream
