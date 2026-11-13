"""Telegram outbox event formatting and per-item delivery policy."""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Awaitable, Callable

from .formatting import TelegramAPIError, _esc
from .config import TelegramConfig, TelegramContext

class TelegramOutboxDeliveryMixin:
    # Shared bot services are supplied by TelegramBot's other mixins.
    config: TelegramConfig
    ctx: TelegramContext
    _rate_limit: Callable[[int], Awaitable[None]]
    send: Callable[[int, str, list[list[dict[str, str]]] | None], Awaitable[int | None]]
    api: Callable[..., Awaitable[Any]]

    def _event_text(self, event: dict[str, Any]) -> str:
        event_id = int(event["event_id"])
        acknowledged = "\n<b>Trạng thái:</b> đã được xác nhận trên hệ thống trước khi gửi" if event.get("acknowledged") else ""
        return (f"{'🚨' if event.get('severity') == 'severe' else '⚠️'} "
            f"<b>{_esc(event.get('severity'))}</b> · <b>#{event_id}</b>\n"
            f"{_esc(event.get('event_type'))}: {_esc(event.get('message'))}\n"
            f"Thời điểm: {_esc(event.get('event_at'))}{acknowledged}")

    async def _process_outbox_item(self, chat_id: int, event: dict[str, Any]) -> None:
        event_id = int(event["event_id"])
        if event.get("text_status") == "pending":
            keyboard = [[{"text": "✅ Đã xử lý", "callback_data": f"ack:{event_id}"}]]
            await self._rate_limit(chat_id)
            try:
                message_id = await self.send(chat_id, self._event_text(event), keyboard)
                await asyncio.to_thread(self.ctx.mark_text, chat_id, event_id, int(message_id or 0))
            except asyncio.CancelledError:
                raise
            except TelegramAPIError as exc:
                if exc.status_code == 401 or exc.status_code == 404:
                    # Global circuit breaker: no cursor/outbox success is recorded.
                    return
                if exc.status_code == 429:
                    delay = max(1, int(exc.retry_after or 1))
                    permanent = False
                elif exc.status_code == 403:
                    delay, permanent = 300, False  # chat may unblock the bot later
                elif exc.status_code == 400:
                    delay, permanent = 0, True
                elif exc.status_code is not None and 400 <= exc.status_code < 500:
                    delay, permanent = 0, True
                else:
                    attempts = int(event.get("text_attempts") or 0)
                    delay, permanent = min(900, 2 ** min(attempts, 9)), False
                await asyncio.to_thread(self.ctx.retry_text, chat_id, event_id,
                    f"{exc.method} HTTP {exc.status_code or 'network'} {exc.description}".strip(), delay, permanent)
                return
            except Exception as exc:
                attempts = int(event.get("text_attempts") or 0)
                await asyncio.to_thread(self.ctx.retry_text, chat_id, event_id,
                    f"send failure: {type(exc).__name__}", min(900, 2 ** min(attempts, 9)), False)
                return
        # Photo is an independent branch. Text and ACK remain delivered even if
        # evidence is unavailable, delayed, expired, or rejected by Telegram.
        refreshed = await asyncio.to_thread(self.ctx.due_items, chat_id, 100)
        current = next((x for x in refreshed if int(x["event_id"]) == event_id), None)
        if not current or current.get("text_status") != "sent" or current.get("photo_status") != "pending":
            return
        evidence = await asyncio.to_thread(self.ctx.evidence, event_id)
        state = evidence.get("status", "not_applicable")
        if state == "pending":
            try:
                created = datetime.fromisoformat(str(event.get("created_at")))
                age = (datetime.now(created.tzinfo) - created).total_seconds()
            except Exception:
                age = 0
            if age >= self.config.evidence_ttl_seconds:
                await asyncio.to_thread(self.ctx.mark_photo, chat_id, event_id, "expired", None, "evidence TTL expired", 0)
            else:
                await asyncio.to_thread(self.ctx.mark_photo, chat_id, event_id, "pending", None, None, 5)
            return
        photo = evidence.get("photo")
        if state != "available" or not photo:
            final_state = "expired" if state == "expired" else "not_applicable" if state == "not_applicable" else "failed"
            await asyncio.to_thread(self.ctx.mark_photo, chat_id, event_id, final_state, None, None, 0)
            return
        await self._rate_limit(chat_id)
        try:
            result = await self.api("sendPhoto", {"chat_id": chat_id,
                "reply_to_message_id": int(current.get("text_message_id") or 0),
                "caption": f"Bằng chứng sự kiện #{event_id}"}, photo=photo)
            photo_id = int(result["message_id"]) if isinstance(result, dict) and result.get("message_id") is not None else None
            await asyncio.to_thread(self.ctx.mark_photo, chat_id, event_id, "sent", photo_id, None, 0)
        except asyncio.CancelledError:
            raise
        except TelegramAPIError as exc:
            if exc.status_code in {401, 404}:
                return
            if exc.status_code == 403:
                await asyncio.to_thread(self.ctx.mark_photo, chat_id, event_id, "pending", None, exc.description, 300)
            elif exc.status_code == 429:
                await asyncio.to_thread(self.ctx.mark_photo, chat_id, event_id, "pending", None, exc.description, max(1,int(exc.retry_after or 1)))
            elif exc.status_code is None or exc.status_code >= 500:
                attempts=int(current.get("photo_attempts") or 0)
                await asyncio.to_thread(self.ctx.mark_photo, chat_id,event_id,"pending",None,exc.description,min(900,2**min(attempts,9)))
            else:
                await asyncio.to_thread(self.ctx.mark_photo, chat_id,event_id,"failed",None,f"HTTP {exc.status_code}: {exc.description}",0)
