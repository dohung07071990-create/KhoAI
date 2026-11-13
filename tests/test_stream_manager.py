from backend.app.stream_manager import StreamManager


def test_stream_viewer_lifecycle_and_protocol_counts():
    manager = StreamManager()
    first = manager.connect("usb", "mjpeg")
    second = manager.connect("usb", "webrtc")
    snapshot = manager.snapshot()
    assert snapshot["streams"]["usb"]["viewers"] == 2
    assert snapshot["streams"]["usb"]["protocols"] == {"mjpeg": 1, "webrtc": 1}
    assert manager.disconnect("usb", first) is True
    assert manager.disconnect("usb", first) is False
    assert manager.snapshot()["streams"]["usb"]["viewers"] == 1
    assert manager.disconnect("usb", second) is True
    assert manager.snapshot()["streams"]["usb"]["active"] is False


def test_stream_metrics_are_counted_without_changing_capture_policy():
    manager = StreamManager()
    session = manager.connect("inside", "mjpeg")
    manager.record_frame("inside", 1200, frame_age_ms=33.2, latency_ms=18.5)
    stream = manager.snapshot()["streams"]["inside"]
    assert stream["frames_sent"] == 1
    assert stream["bytes_sent"] == 1200
    assert stream["last_frame_age_ms"] == 33.2
    assert stream["last_frame_latency_ms"] == 18.5
    snapshot = manager.snapshot()
    assert snapshot["capture_policy"] == "independent"
    assert snapshot["ai_policy"] == "always_independent"
    manager.disconnect("inside", session)


def test_stream_manager_rejects_unknown_protocols():
    manager = StreamManager()
    try:
        manager.connect("usb", "unknown")
    except ValueError:
        pass
    else:
        raise AssertionError("Unknown protocol must be rejected")


def test_transport_chunks_count_bytes_without_faking_frame_count():
    manager = StreamManager()
    manager.record_bytes("inside", 512)
    stream = manager.snapshot()["streams"]["inside"]
    assert stream["bytes_sent"] == 512
    assert stream["frames_sent"] == 0
    assert stream["last_frame_at"] is None
