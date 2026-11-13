"""Telegram callback-query handling."""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Awaitable, Callable

from .formatting import TelegramAPIError, parse_event_id
from .config import TelegramContext

logger = logging.getLogger("khoai.telegram")


class TelegramCallbackMixin:
    # Shared authorization and API services come from TelegramBot's mixins.
    ctx: TelegramContext
    _authorized: Callable[[Any, Any], bool]
    api: Callable[..., Awaitable[Any]]

    async def _handle_callback(self, query: dict[str, Any]) -> None:
        query_id = query.get("id")
        message = query.get("message") or {}
        chat = message.get("chat") or {}
        sender = query.get("from") or {}
        chat_id, user_id = chat.get("id"), sender.get("id")
        data = str(query.get("data") or "")

        try:
            if not self._authorized(chat_id, user_id):
                await self.api(
                    "answerCallbackQuery",
                    {"callback_query_id": query_id, "text": "Không được phép"},
                )
                return

            event_id = parse_event_id(data[4:]) if data.startswith("ack:") else None
            if event_id is None:
                await self.api(
                    "answerCallbackQuery",
                    {"callback_query_id": query_id, "text": "ID cảnh báo không hợp lệ"},
                )
                return
            done = await asyncio.to_thread(
                self.ctx.acknowledge, event_id, f"telegram:{user_id}"
            )
            await self.api(
                "answerCallbackQuery",
                {
                    "callback_query_id": query_id,
                    "text": "Đã xác nhận" if done else "Không thể xác nhận",
                },
            )

            if done and message.get("message_id"):
                try:
                    await self.api(
                        "editMessageReplyMarkup",
                        {
                            "chat_id": chat_id,
                            "message_id": message["message_id"],
                            "reply_markup": {"inline_keyboard": []},
                        },
                    )
                except TelegramAPIError:
                    logger.info("Không thể cập nhật nút ACK sau khi xử lý")

        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning("Xử lý callback Telegram thất bại")
            if query_id:
                try:
                    await self.api(
                        "answerCallbackQuery",
                        {
                            "callback_query_id": query_id,
                            "text": "Không thể xử lý thao tác",
                        },
                    )
                except Exception:
                    logger.warning("Không thể phản hồi callback Telegram")
