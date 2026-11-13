import asyncio
import logging

import pytest

from backend.app.services.retention_worker import RetentionWorker


@pytest.mark.asyncio
async def test_retention_worker_prunes_and_logs_deleted_records(monkeypatch, caplog):
    calls = []

    async def fake_to_thread(fn):
        calls.append(fn())
        return calls[-1]

    async def stop_after_first_sleep(_seconds):
        raise asyncio.CancelledError

    monkeypatch.setattr(asyncio, "to_thread", fake_to_thread)
    monkeypatch.setattr(asyncio, "sleep", stop_after_first_sleep)
    worker = RetentionWorker(lambda: {"access_logs_deleted": 2, "security_events_deleted": 0},
                             logging.getLogger("retention-test"), interval_seconds=0.1)
    with caplog.at_level(logging.INFO, logger="retention-test"):
        with pytest.raises(asyncio.CancelledError):
            await worker.run_forever()
    assert len(calls) == 1
    assert "Đã dọn log cũ" in caplog.text


@pytest.mark.asyncio
async def test_retention_worker_isolates_prune_errors(monkeypatch, caplog):
    async def fake_to_thread(_fn):
        raise RuntimeError("db unavailable")

    async def stop_after_first_sleep(_seconds):
        raise asyncio.CancelledError

    monkeypatch.setattr(asyncio, "to_thread", fake_to_thread)
    monkeypatch.setattr(asyncio, "sleep", stop_after_first_sleep)
    worker = RetentionWorker(lambda: {}, logging.getLogger("retention-error-test"))
    with caplog.at_level(logging.ERROR, logger="retention-error-test"):
        with pytest.raises(asyncio.CancelledError):
            await worker.run_forever()
    assert "Dọn log cũ thất bại" in caplog.text
