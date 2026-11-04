"""Smoke checks for cross-project compatibility endpoints."""
def test_app_imports_and_has_integration_routes():
    from backend.app.main import app
    paths = {route.path for route in app.routes}
    assert "/api/rfid/scan" in paths
    assert "/api/device/heartbeat" in paths
    assert "/api/alerts" in paths
    assert "/api/events" in paths
    # Các endpoint chỉ dành cho camera USB ngoài.
    assert "/api/camera/status" in paths
<<<<<<< HEAD
    assert "/api/camera/anti-theft" in paths
=======
>>>>>>> 889d624ef29217e05c01da0b46d761ffd4ee4920
    assert "/api/camera/stream" in paths
    assert "/api/camera/zone" in paths
    assert "/api/camera/events" in paths
    assert "/api/camera/heatmap" in paths
    assert "/api/camera/evidence/{filename}" in paths
