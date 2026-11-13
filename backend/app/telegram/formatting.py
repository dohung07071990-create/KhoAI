"""Telegram message formatting and sanitized API errors."""
from __future__ import annotations
import html
import re
from html.parser import HTMLParser
from typing import Any

class TelegramAPIError(RuntimeError):
    def __init__(self, method: str, status_code: int | None = None,
                 retry_after: int | None = None, description: str = ""):
        self.method = method
        self.status_code = status_code
        self.retry_after = retry_after
        # Keep a sanitized Telegram description for operations; never include URL/token.
        clean = re.sub(r"https?://\S+", "[url]", str(description or ""))
        clean = clean[:240]
        self.description = clean
        suffix = f" (HTTP {status_code})" if status_code else ""
        super().__init__(f"Telegram API {method} thất bại{suffix}" + (f": {clean}" if clean else ""))


def parse_event_id(value: str) -> int | None:
    """Parse a positive SQLite INTEGER ID without allowing overflow."""
    if not re.fullmatch(r"[0-9]{1,19}", value):
        return None
    event_id = int(value)
    return event_id if 1 <= event_id <= 9_223_372_036_854_775_807 else None

class _HTMLTruncator(HTMLParser):
    """Truncate visible text while keeping Telegram HTML tags/entities valid."""
    ALLOWED = {"b", "strong", "i", "em", "u", "ins", "s", "strike", "del", "code", "pre", "a", "blockquote"}

    def __init__(self, limit: int):
        super().__init__(convert_charrefs=False)
        self.limit = max(0, limit)
        self.used = 0
        self.parts: list[str] = []
        self.stack: list[str] = []
        self.done = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self.done or tag not in self.ALLOWED:
            return
        attrs_text = ""
        if tag == "a":
            href = next((v for k, v in attrs if k == "href"), None)
            if href:
                attrs_text = f' href="{html.escape(href, quote=True)}"'
        self.parts.append(f"<{tag}{attrs_text}>")
        self.stack.append(tag)

    def handle_endtag(self, tag: str) -> None:
        if self.done or tag not in self.ALLOWED or tag not in self.stack:
            return
        # Close nested tags up to the matching element to keep valid markup.
        while self.stack:
            current = self.stack.pop()
            self.parts.append(f"</{current}>")
            if current == tag:
                break

    def handle_data(self, data: str) -> None:
        if self.done:
            return
        remaining = self.limit - self.used
        if remaining <= 0:
            self.done = True
            return
        piece = data[:remaining]
        self.parts.append(html.escape(piece, quote=False))
        self.used += len(piece)
        if len(piece) < len(data):
            self.done = True

    def handle_entityref(self, name: str) -> None:
        if not self.done and self.used < self.limit:
            self.parts.append(f"&{name};")
            self.used += 1

    def handle_charref(self, name: str) -> None:
        if not self.done and self.used < self.limit:
            self.parts.append(f"&#{name};")
            self.used += 1

    def result(self) -> str:
        return "".join(self.parts) + "".join(f"</{tag}>" for tag in reversed(self.stack))

def _truncate_html(value: str, limit: int) -> str:
    parser = _HTMLTruncator(limit)
    try:
        parser.feed(value)
        parser.close()
        return parser.result()
    except Exception:
        # Fail closed to plain escaped text if an unexpected fragment is supplied.
        return html.escape(re.sub(r"<[^>]*>", "", value)[:limit])

def _esc(value: Any) -> str:
    return html.escape(str(value if value is not None else "-"))
