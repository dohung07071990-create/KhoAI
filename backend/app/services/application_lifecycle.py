"""FastAPI application startup/shutdown coordination."""
from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Callable


@asynccontextmanager
async def application_lifespan(
    app: Any,
    *,
    initialize_database: Callable[[], None],
    admin_validator: Callable[[str], None],
    load_detector: Callable[[], Any],
    camera_autostart: bool,
    event_sync_worker: Callable[[], Any],
    retention_worker: Callable[[], Any],
    telegram_bot_factory: Callable[[], Any],
    logger: logging.Logger,
) -> AsyncGenerator[None, None]:
    """Preserve startup/shutdown ordering while keeping app dependencies injected."""
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    configured_admin = os.getenv("KHOAI_ADMIN_TOKEN", "").strip()
    if configured_admin:
        try:
            admin_validator(configured_admin)
        except Exception as exc:
            detail = getattr(exc, "detail", str(exc))
            raise RuntimeError(str(detail)) from exc

    initialize_database()
    detector = None
    try:
        detector = load_detector()
        if camera_autostart:
            detector.start()
    except Exception as exc:  # AI remains optional; database/RFID APIs stay available.
        logger.warning(
            "Camera AI không khởi tạo được (%s). Cài `pip install -r ai/requirements.txt`.",
            exc,
        )
        detector = None

    # Start event synchronization even when camera autostart is disabled.
    sync_task = asyncio.create_task(event_sync_worker()) if detector is not None else None
    retention_task = asyncio.create_task(retention_worker())
    telegram_task = None
    try:
        telegram_bot = telegram_bot_factory()
        if telegram_bot is not None:
            telegram_task = asyncio.create_task(telegram_bot.run(), name="khoai-telegram-bot")
            logger.info("Telegram integration enabled")
    except Exception:
        logger.exception("Không thể khởi tạo Telegram integration; KhoAI vẫn tiếp tục hoạt động")

    try:
        yield
    finally:
        for task in (sync_task, retention_task, telegram_task):
            if task is not None:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        for peer in list(app.state.webrtc_peers):
            try:
                await peer.close()
            except Exception:
                logger.debug("Không thể đóng WebRTC peer khi shutdown", exc_info=True)
        app.state.webrtc_peers.clear()
        if detector is not None:
            detector.stop()
