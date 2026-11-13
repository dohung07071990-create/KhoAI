"""Authenticated metadata-only camera stream WebSocket."""
from __future__ import annotations
import asyncio
from urllib.parse import urlsplit
from typing import Any
from fastapi import APIRouter, WebSocket, WebSocketDisconnect


def create_camera_stream_metadata_router(services: Any) -> tuple[APIRouter, Any]:
    router = APIRouter()

    @router.websocket('/ws/camera/streams')
    async def camera_streams_websocket(websocket: WebSocket) -> None:
        """Metadata-only socket; video remains on MJPEG/WebRTC."""
        origin = websocket.headers.get("origin")
        host = websocket.headers.get("host", "")
        if origin:
            origin_host = urlsplit(origin).netloc
            if not origin_host or origin_host.lower() != host.lower():
                await websocket.close(code=4403)
                return
        session_digest = services.session_digest(websocket.cookies.get("khoai_admin_session"))
        try:
            if not await services.session_digest_valid(session_digest):
                await websocket.close(code=4401)
                return
        except asyncio.CancelledError:
            raise
        except Exception:
            services.logger.warning("Không thể xác minh session WebSocket lúc kết nối", exc_info=True)
            await websocket.close(code=1013)
            return
        await websocket.accept()
        manager = services.stream_manager_provider()
        session_id = manager.connect("metadata", "websocket")
        try:
            while True:
                try:
                    valid = await services.session_digest_valid(session_digest)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    services.logger.warning("Không thể xác minh session WebSocket; đóng kết nối fail-closed", exc_info=True)
                    await websocket.close(code=1013)
                    break
                if not valid:
                    await websocket.close(code=4401)
                    break
                await websocket.send_json(manager.snapshot())
                await asyncio.sleep(1.0)
        except WebSocketDisconnect:
            pass
        except asyncio.CancelledError:
            raise
        finally:
            manager.disconnect("metadata", session_id)

    return router, camera_streams_websocket
