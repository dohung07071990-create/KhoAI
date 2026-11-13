from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def test_dashboard_contains_digital_twin_and_live_metrics():
    html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    assert 'id="warehouse-twin"' in html
    assert 'id="twin-event-list"' in html
    assert 'id="vision-state"' in html
    assert 'warehouse-twin.js' in html

def test_three_scene_is_data_driven_and_marks_schematic_positions():
    source = (ROOT / "frontend" / "warehouse-twin.js").read_text(encoding="utf-8")
    assert "three@0.170.0" in source
    assert "data.decision_tracks" in source
    assert "people_in_zone" in source
    assert "const LAYOUT = Object.freeze" in source
    assert "aisleL:-1.36" in source
    assert "restricted:{x0:-2.2,x1:4.3,z0:-8,z1:-5.9}" in source
    assert "function addRack" in source
    assert "addRack(-5.95,-4.05)" in source
    assert "TRACK SIGNALS · NOT MAPPED" not in source
    assert "globalThis.__KHOAI_TEST_THREE__" in source

def test_analytics_uses_backend_stats_not_demo_values():
    app = (ROOT / "frontend" / "app.js").read_text(encoding="utf-8")
    analytics = (ROOT / "frontend" / "warehouse-analytics.js").read_text(encoding="utf-8")
    assert 'api("/api/stats")' in app
    assert "stats.denied_today" in analytics
    assert "stats.alerts_today" in analytics
    assert "vizzu@0.18" in analytics

def test_digital_twin_limitations_are_documented():
    doc = (ROOT / "docs" / "digital-twin-ui.md").read_text(encoding="utf-8")
    assert "chưa được hiệu chuẩn" in doc
    assert "không gán vị trí 3D giả" in doc


def test_digital_twin_resizes_only_from_visible_stage_bounds_and_on_tab_restore():
    twin = (ROOT / "frontend" / "warehouse-twin.js").read_text(encoding="utf-8")
    app = (ROOT / "frontend" / "app.js").read_text(encoding="utf-8")
    assert "stage.getBoundingClientRect()" in twin
    assert "if (w <= 1 || h <= 1) return false" in twin
    assert "khoai-tab-changed" in twin
    assert "requestAnimationFrame(()=>requestAnimationFrame(resize))" in twin
    assert 'new CustomEvent("khoai-tab-changed"' in app

def test_digital_twin_canvas_cannot_expand_stage_from_intrinsic_min_height():
    css = (ROOT / "frontend" / "style.css").read_text(encoding="utf-8")
    assert ".twin-stage canvas{height:100%;min-height:0}" in css
    assert ".twin-stage{height:clamp(450px,42vw,620px);min-height:0}" in css


def test_track_states_render_as_compact_semantic_badges():
    app = (ROOT / "frontend" / "app.js").read_text(encoding="utf-8")
    css = (ROOT / "frontend" / "style.css").read_text(encoding="utf-8")
    for state in ("PASSERBY", "WARNING", "SUSPICIOUS"):
        assert f'{state}:"' in app
    assert 'class="state-badge state-badge--${badgeClass}"' in app
    for badge in ("passerby", "warning", "suspicious"):
        assert f".state-badge--{badge}" in css


def test_digital_twin_has_bounded_interactive_camera_controls():
    html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    twin = (ROOT / "frontend" / "warehouse-twin.js").read_text(encoding="utf-8")
    css = (ROOT / "frontend" / "style.css").read_text(encoding="utf-8")
    assert 'data-twin-action="zoom-in"' in html
    assert 'data-twin-action="zoom-out"' in html
    assert 'data-twin-action="reset"' in html
    assert "MIN_RADIUS=17,MAX_RADIUS=43" in twin
    assert "MIN_POLAR=.28,MAX_POLAR=1.28" in twin
    assert "stage.addEventListener('wheel'" in twin
    assert "stage.addEventListener('contextmenu'" in twin
    assert "lastPinchDistance" in twin
    assert "function resetView()" in twin
    assert "touch-action:none" in css


def test_dev21_interpolates_only_valid_timestamped_spatial_tracks():
    module = (ROOT / "frontend/digital-twin/track-interpolator.js").read_text(encoding="utf-8")
    twin = (ROOT / "frontend/warehouse-twin.js").read_text(encoding="utf-8")
    detector = (ROOT / "ai/person_detector.py").read_text(encoding="utf-8")
    assert "mapping_valid !== true" in module
    assert "calibrationId" in module and "observed_at" in module
    assert "this.staleAfterMs" in module
    assert "activeContextKey" in module
    assert "TrackInterpolator" in twin and "updateSpatialMarkers" in twin
    assert "floor_bounds" in twin and "twin-spatial-status" in twin
    assert '"observed_at": datetime.now(BUSINESS_TZ)' in detector
    assert "Decision Engine" in (ROOT / "docs/digital-twin-ui.md").read_text(encoding="utf-8")
