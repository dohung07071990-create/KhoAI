"""Experimental WebRTC offer endpoint and peer lifecycle."""
from __future__ import annotations
import asyncio
import os
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Request


def create_camera_webrtc_router(services: Any) -> tuple[APIRouter, Any]:
    router = APIRouter()

    @router.post('/api/camera/webrtc/offer', dependencies=[Depends(services.require_admin)])
    async def camera_webrtc_offer(request: Request) -> dict[str, Any]:
        """Experimental WebRTC output with bounded pending peers and deterministic cleanup."""
        pc = None
        app = services.app_provider()
        try:
            payload = await request.json()
            if not isinstance(payload, dict) or not payload.get("sdp") or not payload.get("type"):
                raise HTTPException(status_code=400, detail="Thiếu SDP offer.")
            peers = app.state.webrtc_peers
            try:
                max_peers = min(32, max(1, int(os.getenv("KHOAI_WEBRTC_MAX_PEERS", "4"))))
            except ValueError:
                max_peers = 4
            if len(peers) >= max_peers:
                raise HTTPException(status_code=429, detail="Đã đạt giới hạn kết nối WebRTC; hãy thử lại sau.")
            detector = services.detector_provider()
            create_peer_connection = services.create_peer_connection_provider()
            detector.start()
            peer_connection, description_type = create_peer_connection(detector, services.stream_manager_provider())
            pc = peer_connection  # Optional cleanup handle for the outer exception handlers.
            peers.add(peer_connection)
            lifecycle = {"session": None, "closed": False, "timeout_task": None}

            async def cleanup_peer() -> None:
                if lifecycle["closed"]:
                    return
                lifecycle["closed"] = True
                if lifecycle["session"] is not None:
                    services.stream_manager_provider().disconnect("usb", lifecycle["session"])
                    lifecycle["session"] = None
                peers.discard(peer_connection)
                timeout_task = lifecycle["timeout_task"]
                if timeout_task is not None and timeout_task is not asyncio.current_task():
                    timeout_task.cancel()
                try:
                    await peer_connection.close()
                except Exception:
                    services.logger.debug("WebRTC peer cleanup failed", exc_info=True)

            @peer_connection.on("connectionstatechange")
            async def on_connectionstatechange():
                state = peer_connection.connectionState
                if state == "connected" and lifecycle["session"] is None:
                    lifecycle["session"] = services.stream_manager_provider().connect("usb", "webrtc")
                elif state in {"failed", "closed", "disconnected"}:
                    await cleanup_peer()

            async def expire_pending_peer() -> None:
                await asyncio.sleep(15)
                if not lifecycle["closed"] and peer_connection.connectionState != "connected":
                    await cleanup_peer()

            await peer_connection.setRemoteDescription(description_type(sdp=str(payload["sdp"]), type=str(payload["type"])))
            answer = await peer_connection.createAnswer()
            await peer_connection.setLocalDescription(answer)
            lifecycle["timeout_task"] = asyncio.create_task(expire_pending_peer())
            return {"sdp": peer_connection.localDescription.sdp, "type": peer_connection.localDescription.type}
        except HTTPException:
            if pc is not None:
                try:
                    await pc.close()
                finally:
                    app.state.webrtc_peers.discard(pc)
            raise
        except RuntimeError as exc:
            services.logger.exception("WebRTC negotiation unavailable")
            if pc is not None:
                try:
                    await pc.close()
                finally:
                    app.state.webrtc_peers.discard(pc)
            raise HTTPException(status_code=503, detail="WebRTC hiện không khả dụng.") from exc
        except Exception as exc:
            if pc is not None:
                try:
                    await pc.close()
                except Exception:
                    services.logger.debug("WebRTC negotiation cleanup failed", exc_info=True)
                app.state.webrtc_peers.discard(pc)
            services.logger.exception("Không tạo được WebRTC peer")
            raise HTTPException(status_code=503, detail="Không thể khởi tạo WebRTC lúc này.") from exc

    return router, camera_webrtc_offer
