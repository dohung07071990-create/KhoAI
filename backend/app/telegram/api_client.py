"""Telegram HTTP API operations for the bot adapter."""
from __future__ import annotations
import httpx
import html
import re
import time
from typing import Any
from .formatting import TelegramAPIError, _truncate_html
from .config import TelegramConfig, TelegramContext

class TelegramAPIMixin:
    # Runtime dependencies are initialized by TelegramBot.
    config: TelegramConfig
    client: httpx.AsyncClient
    ctx: TelegramContext
    _auth_blocked: bool
    _last_auth_probe: float

    async def api(self, method: str, data: dict[str, Any] | None = None,
                  photo: bytes | None = None) -> Any:
        url = f"{self.config.api_base}/bot{self.config.token}/{method}"
        try:
            if photo is not None:
                response = await self.client.post(url, data=data or {},
                    files={"photo": ("khoai-evidence.jpg", photo, "image/jpeg")})
            else:
                response = await self.client.post(url, json=data or {})
            try:
                payload = response.json()
            except Exception:
                payload = {}
            code = response.status_code if response.status_code >= 400 else payload.get("error_code")
            if response.status_code >= 400 or not payload.get("ok"):
                retry_after = None
                parameters = payload.get("parameters")
                if isinstance(parameters, dict):
                    raw_retry_after = parameters.get("retry_after")
                    if isinstance(raw_retry_after, (int, float, str)):
                        try:
                            retry_after = int(raw_retry_after)
                        except (TypeError, ValueError):
                            pass
                description = str(payload.get("description") or "").replace(self.config.token, "[token]")
                if code in {401, 404}:
                    self._auth_blocked = True
                    self._last_auth_probe = time.monotonic()
                    try:
                        self.ctx.runtime_state("circuit_breaker", "OPEN")
                        self.ctx.runtime_state("last_error", f"{method} HTTP {code}: {description}")
                    except Exception:
                        pass
                raise TelegramAPIError(method, int(code) if code else None, retry_after, description)
            return payload.get("result")
        except TelegramAPIError:
            raise
        except httpx.HTTPError:
            raise TelegramAPIError(method, description="network error or timeout") from None

    async def send(self, chat_id: int, message: str,
                   keyboard: list[list[dict[str, str]]] | None = None) -> int | None:
        data: dict[str, Any] = {"chat_id": chat_id, "text": _truncate_html(message, 4000),
            "parse_mode": "HTML", "link_preview_options": {"is_disabled": True}}
        if keyboard:
            data["reply_markup"] = {"inline_keyboard": keyboard}
        try:
            result = await self.api("sendMessage", data)
        except TelegramAPIError as exc:
            if exc.status_code == 400 and "parse entities" in exc.description.lower():
                plain = html.unescape(re.sub(r"<[^>]*>", "", message))[:4000]
                fallback = {"chat_id": chat_id, "text": plain}
                if keyboard:
                    fallback["reply_markup"] = {"inline_keyboard": keyboard}
                result = await self.api("sendMessage", fallback)
            else:
                raise
        return int(result["message_id"]) if isinstance(result, dict) and result.get("message_id") is not None else None
