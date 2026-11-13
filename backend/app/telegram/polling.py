"""Telegram polling loop and authentication recovery."""
from __future__ import annotations
import asyncio
import logging
import time
from typing import Any, Awaitable, Callable
from .formatting import TelegramAPIError
from .config import TelegramConfig, TelegramContext

logger = logging.getLogger("khoai.telegram")

class TelegramPollingMixin:
    # These members are supplied by TelegramBot or its other mixins.
    config: TelegramConfig
    ctx: TelegramContext
    _offset: int
    _auth_blocked: bool
    _last_auth_probe: float
    _last_chat_send: dict[int, float]
    api: Callable[..., Awaitable[Any]]
    handle_update: Callable[[dict[str, Any]], Awaitable[None]]

    async def command_loop(self) -> None:
        try:
            await self.api("deleteWebhook", {"drop_pending_updates": False})
        except Exception:
            logger.warning("Không thể xóa webhook Telegram cũ; sẽ tiếp tục polling")
        while True:
            try:
                if self._auth_blocked:
                    await self._probe_auth()
                    await asyncio.sleep(2)
                    continue
                updates = await self.api("getUpdates", {"offset": self._offset,
                    "timeout": self.config.poll_timeout, "allowed_updates": ["message", "callback_query"]})
                for update in updates or []:
                    self._offset = int(update["update_id"]) + 1
                    try:
                        await self.handle_update(update)
                    except Exception:
                        logger.exception("Xử lý một Telegram update thất bại")
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.warning("Telegram polling lỗi; thử lại sau 5 giây")
                await asyncio.sleep(5)

    async def _rate_limit(self, chat_id: int) -> None:
        now = time.monotonic()
        wait = 1.0 - (now - self._last_chat_send.get(chat_id, 0.0))
        if wait > 0:
            await asyncio.sleep(wait)
        self._last_chat_send[chat_id] = time.monotonic()

    async def _probe_auth(self) -> bool:
        if not self._auth_blocked:
            return True
        if time.monotonic() - self._last_auth_probe < self.config.auth_probe_interval:
            return False
        self._last_auth_probe = time.monotonic()
        try:
            await self.api("getMe", {})
            self._auth_blocked = False
            try:
                self.ctx.runtime_state("circuit_breaker", "CLOSED")
            except Exception:
                pass
            logger.info("Telegram authentication recovered")
            return True
        except TelegramAPIError:
            return False
