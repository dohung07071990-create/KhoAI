"""Telegram adapter facade and worker supervisor.

Configuration, lease policy, command, API, formatting, and outbox
responsibilities live in focused modules. This module preserves the historic
TelegramBot and helper import surface.
"""
from __future__ import annotations

import asyncio
import logging
import secrets

import httpx

from .formatting import TelegramAPIError, _HTMLTruncator, _truncate_html, _esc
from .api_client import TelegramAPIMixin
from .commands import TelegramCommandMixin
from .notifier import TelegramNotifierMixin
from .config import TelegramConfig, TelegramContext, load_config, telegram_enabled
from .lease import _lease_heartbeat_loop

logger = logging.getLogger("khoai.telegram")
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

class TelegramBot(TelegramAPIMixin, TelegramCommandMixin, TelegramNotifierMixin):

    def __init__(self, config: TelegramConfig, context: TelegramContext,
                 client: httpx.AsyncClient | None = None) -> None:
        self.config = config
        self.ctx = context
        self.client = client or httpx.AsyncClient(timeout=httpx.Timeout(config.poll_timeout + 10, connect=10))
        self._owns_client = client is None
        self._offset = 0
        self._owner = secrets.token_hex(16)
        self._auth_blocked = False
        self._last_auth_probe = 0.0
        self._last_chat_send: dict[int, float] = {}

    async def run(self) -> None:
        """Run with lease retry and in-process recovery for transient DB/task failures."""
        retry_delay = 1.0
        try:
            while True:
                try:
                    acquired = await asyncio.to_thread(self.ctx.lease, "acquire", self._owner, 60)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.warning("Telegram lease acquire lỗi tạm thời; sẽ thử lại", exc_info=True)
                    await asyncio.sleep(retry_delay)
                    retry_delay = min(15.0, retry_delay * 2)
                    continue
                if not acquired:
                    # Another instance may own the lease, or a killed instance's
                    # lease may still be alive. Keep waiting instead of exiting.
                    await asyncio.sleep(retry_delay)
                    retry_delay = min(15.0, retry_delay * 2)
                    continue
                retry_delay = 1.0
                tasks = [asyncio.create_task(self.command_loop()),
                         asyncio.create_task(self.notifier_loop()),
                         asyncio.create_task(_lease_heartbeat_loop(self.ctx.lease, self._owner, 60))]
                try:
                    await asyncio.gather(*tasks)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.exception("Telegram worker gặp lỗi; sẽ khởi động lại sau backoff")
                finally:
                    for task in tasks:
                        task.cancel()
                    await asyncio.gather(*tasks, return_exceptions=True)
                    try:
                        await asyncio.to_thread(self.ctx.lease, "release", self._owner, 60)
                    except Exception:
                        logger.warning("Không giải phóng được Telegram lease; lease sẽ tự hết hạn")
                await asyncio.sleep(retry_delay)
                retry_delay = min(15.0, retry_delay * 2)
        finally:
            if self._owns_client:
                await self.client.aclose()
