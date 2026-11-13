from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.routes.camera_evidence import create_camera_evidence_router
from backend.app.routes.camera_frames import create_camera_frame_router
from backend.app.routes.camera_media import create_camera_media_router
from tests._route_utils import iter_registered_routes


class _Detector:
    def track_thumbnail_jpeg(self, _track_id):
        return b"thumb"

    def heatmap_jpeg(self):
        return b"heatmap"

    def snapshot_jpeg(self, annotated=False):
        assert annotated is False
        return b"snapshot"


def _services(tmp_path):
    return SimpleNamespace(
        require_admin_query=lambda: None,
        detector_provider=lambda: _Detector(),
        stream_manager_provider=lambda: SimpleNamespace(snapshot=lambda: {"usb": 1}),
        ensure_camera_for_read=lambda _request, _detector: None,
        evidence_dir_provider=lambda: tmp_path,
        logger=SimpleNamespace(exception=lambda *args, **kwargs: None),
    )


def test_camera_media_split_and_compatibility_facade_preserve_paths(tmp_path):
    evidence = tmp_path / ("a" * 32 + ".jpg")
    evidence.write_bytes(b"evidence")
    services = _services(tmp_path)

    isolated = FastAPI()
    isolated.include_router(create_camera_frame_router(services))
    isolated.include_router(create_camera_evidence_router(services))
    client = TestClient(isolated)
    assert client.get("/api/camera/streams/status").json() == {"usb": 1}
    assert client.get("/api/camera/tracks/7/thumbnail").content == b"thumb"
    assert client.get("/api/camera/heatmap").content == b"heatmap"
    assert client.get("/api/camera/snapshot").content == b"snapshot"
    assert client.get(f"/api/camera/evidence/{evidence.name}").content == b"evidence"
    assert client.get("/api/camera/evidence/not-a-uuid.jpg").status_code == 404

    facade = FastAPI()
    facade.include_router(create_camera_media_router(services))
    paths = [route.path for route in iter_registered_routes(facade.routes)]
    assert paths.count("/api/camera/streams/status") == 1
    assert paths.count("/api/camera/evidence/{filename}") == 1
    assert paths.count("/api/camera/snapshot") == 1
