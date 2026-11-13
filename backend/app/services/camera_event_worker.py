"""Background worker coordinating USB camera event persistence and reconciliation."""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable


class CameraEventSyncWorker:
    """Poll detector events and run persistence/reconciliation callbacks.

    The worker owns polling cadence and error isolation only. Event semantics,
    persistence, and incident decisions remain in their respective services.
    """

    def __init__(self, detector_provider: Callable[[], Any],
                 sync_events: Callable[[list[dict[str, Any]]], None],
                 reconcile_incidents: Callable[[], None],
                 logger: logging.Logger, interval_seconds: float = 0.5,
                 batch_size: int = 100) -> None:
        self.detector_provider = detector_provider
        self.sync_events = sync_events
        self.reconcile_incidents = reconcile_incidents
        self.logger = logger
        self.interval_seconds = max(0.05, float(interval_seconds))
        self.batch_size = max(1, int(batch_size))

    async def run_forever(self) -> None:
        while True:
            try:
                detector = self.detector_provider()
                events = detector.get_events(self.batch_size)
                await asyncio.to_thread(self.sync_events, events)
                await asyncio.to_thread(self.reconcile_incidents)
            except asyncio.CancelledError:
                raise
            except Exception:
                self.logger.exception("Đồng bộ sự kiện camera USB thất bại")
            await asyncio.sleep(self.interval_seconds)
