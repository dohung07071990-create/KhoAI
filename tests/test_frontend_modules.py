from pathlib import Path
import re

from tests._route_utils import iter_registered_routes

ROOT = Path(__file__).resolve().parents[1]


def test_dashboard_bootstrap_is_an_es_module_and_loads_shared_modules():
    html = (ROOT / "frontend/index.html").read_text(encoding="utf-8")
    app = (ROOT / "frontend/app.js").read_text(encoding="utf-8")
    assert '<script type="module" src="app.js"></script>' in html
    assert "from './core/constants.js'" in app
    assert "from './core/state.js'" in app
    assert "from './core/events.js'" in app


def test_all_local_module_imports_resolve():
    for source in (ROOT / "frontend").rglob("*.js"):
        content = source.read_text(encoding="utf-8")
        for rel in re.findall("from\\s+['\"]([^'\"]+)['\"]", content):
            if rel.startswith("."):
                assert (source.parent / rel).resolve().is_file(), (source, rel)


def test_homography_and_webrtc_are_opt_in():
    example = (ROOT / "ai/homography.example.json").read_text(encoding="utf-8")
    from backend.app.main import app
    assert '"enabled": false' in example
    assert any(route.path == "/api/camera/webrtc/offer" and "POST" in getattr(route, "methods", set()) for route in iter_registered_routes(app.routes))
    assert "requirements-webrtc.txt" in (ROOT / "backend/app/webrtc.py").read_text(encoding="utf-8")


def test_authentication_and_api_transport_are_separate_modules():
    app = (ROOT / "frontend/app.js").read_text(encoding="utf-8")
    auth = (ROOT / "frontend/auth/auth-manager.js").read_text(encoding="utf-8")
    api = (ROOT / "frontend/core/api.js").read_text(encoding="utf-8")
    assert "createAuthManager" in app
    assert "createApiClient" in app
    assert "function showAccountLogin" in auth
    assert "requestAdminToken" in auth
    assert "createApiClient" in api
    assert "X-Admin-Token" in api


def test_dynamic_stream_manager_is_wired_as_metadata_only_channel():
    root = Path(__file__).resolve().parents[1]
    from backend.app.main import app as backend_app
    main = (root / "backend/app/main.py").read_text(encoding="utf-8")
    app = (root / "frontend/app.js").read_text(encoding="utf-8")
    html = (root / "frontend/index.html").read_text(encoding="utf-8")
    assert any(
        route.path == "/api/camera/streams/status"
        and "GET" in (getattr(route, "methods", None) or set())
        for route in iter_registered_routes(backend_app.routes)
    )
    assert any(
        route.path == "/ws/camera/streams"
        and getattr(route, "methods", None) is None
        for route in iter_registered_routes(backend_app.routes)
    )
    assert 'initStreamMetrics();' in app
    assert 'id="stream-distribution-status"' in html
    assert 'manager.disconnect("usb", session_id)' in main
    assert 'manager.disconnect("inside", lifecycle["session_id"])' in main
    assert 'background=BackgroundTask(cleanup)' in main
    assert 'manager.record_bytes("inside", len(chunk))' in main


def test_stream_metrics_has_watchdog_and_stops_retrying_expired_sessions():
    source = (ROOT / "frontend/camera/stream-metrics.js").read_text(encoding="utf-8")
    assert "Date.now() - lastMessageAt > 5000" in source
    assert "event.code === 4401" in source
    assert "if (event.code === 4401) return" in source
