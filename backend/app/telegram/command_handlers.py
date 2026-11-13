"""Telegram command handler methods."""
from __future__ import annotations
import asyncio
import logging
from typing import Any, Awaitable, Callable
from .formatting import _esc, parse_event_id
from .config import TelegramConfig, TelegramContext

logger = logging.getLogger("khoai.telegram")

class TelegramCommandHandlersMixin:
    # Shared bot services are supplied by TelegramBot and its other mixins.
    config: TelegramConfig
    ctx: TelegramContext
    _handle_callback: Callable[[Any], Awaitable[None]]
    send: Callable[..., Awaitable[Any]]
    api: Callable[..., Awaitable[Any]]

    def _authorized(self, chat_id: Any, user_id: Any) -> bool:
        # Only private chats are accepted. This prevents an allowlisted user from
        # accidentally exposing warehouse status in a group chat.
        return isinstance(chat_id, int) and chat_id == user_id and chat_id in self.config.allowed_chat_ids

    async def handle_update(self, update: dict[str, Any]) -> None:
        if "callback_query" in update:
            await self._handle_callback(update["callback_query"])
            return
        message = update.get("message") or {}
        chat = message.get("chat") or {}
        sender = message.get("from") or {}
        chat_id, user_id = chat.get("id"), sender.get("id")
        text = (message.get("text") or "").strip()
        if not text.startswith("/") or not isinstance(chat_id, int):
            return
        command, *args = text.split()
        command = command.split("@", 1)[0].lower()
        if command == "/id" and not self._authorized(chat_id, user_id):
            if chat.get("type") == "private" and chat_id == user_id:
                await self.send(chat_id, f"Chat ID: <code>{chat_id}</code>. Hãy nhờ quản trị viên thêm ID này vào allowlist.")
            return
        if command == "/start" and not self._authorized(chat_id, user_id):
            return
        if not self._authorized(chat_id, user_id):
            return
        if command in {"/start", "/help"}:
            await self.send(chat_id, "<b>KhoAI Bot</b>\n/status – trạng thái hệ thống\n/alerts – cảnh báo chưa xử lý\n/ack &lt;id&gt; – xác nhận một cảnh báo\n/ackall – xác nhận tất cả cảnh báo đang mở\n/snapshot – ảnh camera hiện tại\n/id – Chat ID")
        elif command == "/id":
            await self.send(chat_id, f"Chat ID: <code>{chat_id}</code>")
        elif command == "/status":
            status = await asyncio.to_thread(self.ctx.status)
            await self.send(chat_id, "<b>Trạng thái KhoAI</b>\n" + "\n".join(
                f"{_esc(k)}: <b>{_esc(v)}</b>" for k, v in status.items()))
        elif command == "/alerts":
            alerts = await asyncio.to_thread(self.ctx.alerts, 10)
            if not alerts:
                await self.send(chat_id, "✅ Không có cảnh báo chưa xử lý.")
                return
            lines, buttons = [], []
            for event in alerts:
                event_id = int(event["id"])
                lines.append(f"{_esc(event.get('severity'))} <b>#{event_id}</b> · {_esc(event.get('event_at'))}\n{_esc(event.get('message'))}")
                buttons.append({"text": f"ACK #{event_id}", "callback_data": f"ack:{event_id}"})
            keyboard = [buttons[i:i+3] for i in range(0, len(buttons), 3)]
            await self.send(chat_id, "<b>Cảnh báo chưa xử lý</b>\n" + "\n\n".join(lines), keyboard)
        elif command == "/ack":
            event_id = parse_event_id(args[0]) if len(args) == 1 else None
            if event_id is None:
                await self.send(chat_id, "Cú pháp: <code>/ack 123</code>")
                return
            done = await asyncio.to_thread(self.ctx.acknowledge, event_id, f"telegram:{user_id}")
            await self.send(chat_id, "✅ Đã xác nhận cảnh báo." if done else "Không tìm thấy cảnh báo hoặc cảnh báo đã được xác nhận.")
        elif command == "/ackall":
            count = await asyncio.to_thread(self.ctx.acknowledge_all, f"telegram:{user_id}")
            await self.send(chat_id, f"✅ Đã xác nhận {count} cảnh báo.")
        elif command == "/snapshot":
            jpeg = await asyncio.to_thread(self.ctx.snapshot)
            if not jpeg:
                await self.send(chat_id, "Camera chưa có khung hình.")
            else:
                await self.api("sendPhoto", {"chat_id": chat_id, "caption": "Ảnh camera KhoAI"}, photo=jpeg)
        else:
            await self.send(chat_id, "Lệnh không hỗ trợ. Gõ /help.")
