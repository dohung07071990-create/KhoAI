from __future__ import annotations

import asyncio
import logging

import pytest

from backend.app.services.camera_event_worker import CameraEventSyncWorker


class _Detector:
    def __init__(self, events):
        self.events = events
        self.requested_batch = None

    def get_events(self, limit):
        self.requested_batch = limit
        return self.events


@pytest.mark.asyncio
async def test_worker_polls_and_runs_sync_then_reconciliation(monkeypatch):
    detector = _Detector([{"event_id": "evt-1"}])
    calls = []

    async def stop_after_sleep(_seconds):
        raise asyncio.CancelledError

    monkeypatch.setattr(asyncio, "sleep", stop_after_sleep)
    worker = CameraEventSyncWorker(
        detector_provider=lambda: detector,
        sync_events=lambda events: calls.append(("sync", events)),
        reconcile_incidents=lambda: calls.append(("reconcile", None)),
        logger=logging.getLogger("test.camera.worker"), batch_size=17,
    )

    with pytest.raises(asyncio.CancelledError):
        await worker.run_forever()

    assert detector.requested_batch == 17
    assert calls == [("sync", [{"event_id": "evt-1"}]), ("reconcile", None)]


@pytest.mark.asyncio
async def test_worker_continues_after_detector_error(monkeypatch):
    calls = []

    async def stop_after_sleep(_seconds):
        raise asyncio.CancelledError

    monkeypatch.setattr(asyncio, "sleep", stop_after_sleep)
    worker = CameraEventSyncWorker(
        detector_provider=lambda: (_ for _ in ()).throw(RuntimeError("offline")),
        sync_events=lambda events: calls.append(events),
        reconcile_incidents=lambda: calls.append("reconcile"),
        logger=logging.getLogger("test.camera.worker"),
    )

    with pytest.raises(asyncio.CancelledError):
        await worker.run_forever()

    assert calls == []
