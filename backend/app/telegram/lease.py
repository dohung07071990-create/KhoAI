"""Telegram distributed-worker lease heartbeat policy."""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable

logger = logging.getLogger("khoai.telegram")


async def _lease_heartbeat_loop(lease: Callable[..., bool], owner: str, ttl: int = 60,
                                interval: float = 20.0,
                                sleep: Callable[[float], Any] = asyncio.sleep,
                                monotonic: Callable[[], float] = time.monotonic,
                                safety_margin: float = 5.0) -> None:
    """Renew lease, but stop the worker before an uncertain lease can expire.

    A successful acquire/renew establishes a local expiry deadline. Transient
    SQLite errors are retried only while enough time remains to prove ownership.
    If that deadline is approached, raise so the supervisor cancels polling and
    releases resources rather than allowing a second process to poll concurrently.
    """
    last_confirmed = monotonic()
    while True:
        await sleep(interval)
        failures = 0
        while True:
            remaining = ttl - (monotonic() - last_confirmed)
            safe_remaining = remaining - max(0.0, safety_margin)
            if safe_remaining <= 0:
                raise RuntimeError("Telegram lease renewal unconfirmed before expiry; stopping worker")
            try:
                call = asyncio.to_thread(lease, "renew", owner, ttl)
                ok = await asyncio.wait_for(call, timeout=safe_remaining)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                failures += 1
                remaining = ttl - (monotonic() - last_confirmed)
                safe_remaining = remaining - max(0.0, safety_margin)
                if safe_remaining <= 0:
                    raise RuntimeError("Telegram lease renewal failed near expiry; stopping worker") from exc
                delay = min(5.0, float(failures), safe_remaining)
                logger.warning("Telegram lease heartbeat lỗi tạm thời (%s); thử lại sau %.1fs", failures, delay)
                await sleep(delay)
                continue
            if not ok:
                raise RuntimeError("Telegram lease lost")
            last_confirmed = monotonic()
            break
