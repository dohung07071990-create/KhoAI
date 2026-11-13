"""Browser security headers for the dashboard and API responses."""
from __future__ import annotations

import os
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class SecurityHeadersMiddleware:
    """Apply restrictive browser policy; CDN dependencies must be self-hosted."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_security_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                existing = {key.lower() for key, _ in headers}
                policy = (
                    "default-src 'self'; base-uri 'self'; object-src 'none'; "
                    "frame-ancestors 'none'; form-action 'self'; script-src 'self'; "
                    "style-src 'self'; style-src-attr 'unsafe-inline'; "
                    "img-src 'self' data: blob: https:; "
                    "font-src 'self' data:; media-src 'self' blob:; "
                    "connect-src 'self' ws: wss:; worker-src 'self' blob:"
                )
                policy_header = (
                    b"content-security-policy"
                    if os.getenv("KHOAI_CSP_MODE", "report-only").strip().lower() == "enforce"
                    else b"content-security-policy-report-only"
                )
                security = {
                    policy_header: policy.encode("ascii"),
                    b"x-content-type-options": b"nosniff",
                    b"x-frame-options": b"DENY",
                    b"referrer-policy": b"strict-origin-when-cross-origin",
                    b"permissions-policy": b"camera=(), microphone=(), geolocation=()",
                }
                for key, value in security.items():
                    if key not in existing:
                        headers.append((key, value))
                if scope.get("scheme") == "https" and b"strict-transport-security" not in existing:
                    headers.append((b"strict-transport-security", b"max-age=31536000; includeSubDomains"))
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_with_security_headers)
