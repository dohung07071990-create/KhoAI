"""Digest policy for delayed Telegram WARNING notifications."""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Awaitable, Callable

from .formatting import TelegramAPIError, _esc
from .config import TelegramConfig, TelegramContext

class TelegramWarningDigestMixin:
    # Shared bot services are supplied by TelegramBot's other mixins.
    config: TelegramConfig
    ctx: TelegramContext
    _rate_limit: Callable[[int], Awaitable[None]]
    send: Callable[[int, str, list[list[dict[str, str]]] | None], Awaitable[int | None]]

    async def _summarize_delayed_warnings(self, chat_id: int, events: list[dict[str, Any]]) -> set[int]:
        """Coalesce a large delayed warning backlog; severe events remain individual."""
        now = datetime.now().astimezone()
        delayed = []
        for event in events:
            if event.get("severity") != "warning" or event.get("text_status") != "pending":
                continue
            if bool(event.get("replay_pending")):
                delayed.append(event)
                continue
            try:
                created = datetime.fromisoformat(str(event.get("created_at")))
                if (now - created).total_seconds() >= self.config.warning_summary_after_seconds:
                    delayed.append(event)
            except (TypeError, ValueError):
                continue
        if len(delayed) < 20:
            return set()
        summarized: set[int] = set()
        for offset in range(0, len(delayed), 20):
            batch = delayed[offset:offset + 20]
            lines = [f"#{int(item['event_id'])} · {_esc(item.get('event_at'))} · {_esc(item.get('event_type'))}" for item in batch]
            buttons = [[{"text": f"ACK #{int(item['event_id'])}", "callback_data": f"ack:{int(item['event_id'])}"}] for item in batch]
            replay_count = sum(bool(item.get("replay_pending")) for item in batch)
            title = "Cảnh báo phát lại sau nâng cấp" if replay_count else "Cảnh báo WARNING bị trì hoãn"
            message = (f"<b>KhoAI · Tổng hợp {title}</b>\n"
                       f"{len(batch)} cảnh báo được gộp để tránh gửi dồn từng tin.\n" + "\n".join(lines))
            await self._rate_limit(chat_id)
            try:
                message_id = await self.send(chat_id, message, buttons)
                for item in batch:
                    event_id = int(item["event_id"])
                    await asyncio.to_thread(self.ctx.mark_text, chat_id, event_id, int(message_id or 0))
                    # A summary represents the delayed WARNING text delivery;
                    # do not fan out one evidence photo per summarized event.
                    await asyncio.to_thread(self.ctx.mark_photo, chat_id, event_id,
                                            "not_applicable", None, "included in delayed-warning summary", 0)
                    summarized.add(event_id)
            except asyncio.CancelledError:
                raise
            except TelegramAPIError as exc:
                if exc.status_code in {401, 404}:
                    return summarized
                delay = max(1, int(exc.retry_after or 1)) if exc.status_code == 429 else 300 if exc.status_code == 403 else min(900, 2 ** 8)
                permanent = bool(exc.status_code and 400 <= exc.status_code < 500 and exc.status_code not in {403, 429})
                for item in batch:
                    event_id = int(item["event_id"])
                    await asyncio.to_thread(self.ctx.retry_text, chat_id, event_id,
                        f"summary {exc.method} HTTP {exc.status_code or 'network'} {exc.description}", delay, permanent)
                    summarized.add(event_id)
        return summarized
