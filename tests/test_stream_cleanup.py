import asyncio

import pytest

from backend.app import main
from backend.app.stream_manager import StreamManager


class FakeUpstream:
    status_code = 200
    headers = {"content-type": "multipart/x-mixed-replace; boundary=frame"}

    def __init__(self):
        self.closed = False

    async def aiter_raw(self):
        yield b"chunk-one"
        yield b"chunk-two"
        await asyncio.Event().wait()

    async def aclose(self):
        self.closed = True


class FakeClient:
    def __init__(self, *args, **kwargs):
        self.upstream = FakeUpstream()
        self.closed = False

    def build_request(self, *args, **kwargs):
        return object()

    async def send(self, *args, **kwargs):
        return self.upstream

    async def aclose(self):
        self.closed = True


@pytest.mark.asyncio
async def test_inside_stream_registers_on_body_start_and_cleans_on_cancel(monkeypatch):
    import httpx

    clients = []

    def make_client(*args, **kwargs):
        client = FakeClient(*args, **kwargs)
        clients.append(client)
        return client

    monkeypatch.setattr(httpx, "AsyncClient", make_client)
    monkeypatch.setenv("KHOAI_ESP32_CAM_STREAM_URL", "http://esp32.local/stream")
    manager = StreamManager()
    monkeypatch.setattr(main.app.state, "stream_manager", manager)

    from starlette.requests import Request
    request = Request({"type": "http", "method": "GET", "path": "/api/camera/inside/stream", "headers": [], "query_string": b"", "server": ("testserver", 80), "client": ("testclient", 50000), "scheme": "http", "state": {"khoai_session_digest": "test-session-digest"}})
    monkeypatch.setattr(main, "_session_digest_valid", lambda _digest: True)
    response = await main.inside_camera_stream(request)
    assert manager.snapshot()["streams"].get("inside", {}).get("viewers", 0) == 0

    iterator = response.body_iterator
    first_chunk = await iterator.__anext__()
    assert first_chunk == b"chunk-one"
    assert manager.snapshot()["streams"]["inside"]["viewers"] == 1
    assert manager.snapshot()["streams"]["inside"]["bytes_sent"] == 0
    second_chunk = await iterator.__anext__()
    assert second_chunk == b"chunk-two"
    assert manager.snapshot()["streams"]["inside"]["bytes_sent"] == len(first_chunk)
    assert manager.snapshot()["streams"]["inside"]["frames_sent"] == 0

    await iterator.aclose()
    await response.background()
    stream = manager.snapshot()["streams"]["inside"]
    assert stream["viewers"] == 0
    assert stream["disconnects_total"] == 1
    assert clients[0].upstream.closed is True
    assert clients[0].closed is True
