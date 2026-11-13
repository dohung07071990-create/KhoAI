"""Background worker for periodic audit and evidence retention."""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable


class RetentionWorker:
    """Own retention scheduling and failure isolation, not retention policy."""

    def __init__(self, prune: Callable[[], dict[str, Any]], logger: logging.Logger,
                 interval_seconds: float = 3600.0) -> None:
        self.prune = prune
        self.logger = logger
        self.interval_seconds = max(1.0, float(interval_seconds))

    async def run_forever(self) -> None:
        while True:
            try:
                result = await asyncio.to_thread(self.prune)
                if result.get("access_logs_deleted") or result.get("security_events_deleted"):
                    self.logger.info("Đã dọn log cũ: %s", result)
            except asyncio.CancelledError:
                raise
            except Exception:
                self.logger.exception("Dọn log cũ thất bại")
            await asyncio.sleep(self.interval_seconds)
