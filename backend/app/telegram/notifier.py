"""Per-chat Telegram notification outbox processing."""
from __future__ import annotations
import asyncio
import logging
from datetime import datetime
from typing import Awaitable, Callable
from .formatting import TelegramAPIError
from .config import TelegramConfig, TelegramContext
from .notifier_delivery import TelegramOutboxDeliveryMixin
from .notifier_digest import TelegramWarningDigestMixin

logger = logging.getLogger("khoai.telegram")

class TelegramNotifierMixin(TelegramOutboxDeliveryMixin, TelegramWarningDigestMixin):
    # Shared state and polling hook are provided by TelegramBot and its mixins.
    config: TelegramConfig
    ctx: TelegramContext
    _auth_blocked: bool
    _probe_auth: Callable[[], Awaitable[bool]]

    async def _process_chat_outbox(self, chat_id: int) -> None:
        try:
            await asyncio.to_thread(self.ctx.discover_events, chat_id, 100)
            events = await asyncio.to_thread(self.ctx.due_items, chat_id, 30)
            summarized = await self._summarize_delayed_warnings(chat_id, events)
            for event in events:
                if self._auth_blocked:
                    break
                if int(event["event_id"]) in summarized:
                    continue
                await self._process_outbox_item(chat_id, event)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning("Telegram notifier lỗi với một chat; các chat khác vẫn tiếp tục")

    async def notifier_loop(self) -> None:
        while True:
            if not await self._probe_auth():
                await asyncio.sleep(self.config.notify_interval)
                continue
            # Chat queues are independent: a blocked chat or its retry schedule
            # cannot delay another administrator's delivery loop.
            await asyncio.gather(*(self._process_chat_outbox(chat_id)
                                   for chat_id in sorted(self.config.allowed_chat_ids)))
            await asyncio.sleep(self.config.notify_interval)
