from collections import Counter
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class MarkupAudit(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = []
        self.headers = []
        self.tabs = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if "id" in attrs:
            self.ids.append(attrs["id"])
        if tag == "th":
            self.headers.append(attrs)
        if tag == "button" and attrs.get("data-t"):
            self.tabs.append(attrs["data-t"])


def test_twin_metrics_are_owned_by_app_not_three_module():
    app = (ROOT / "frontend/app.js").read_text(encoding="utf-8")
    twin = (ROOT / "frontend/warehouse-twin.js").read_text(encoding="utf-8")
    assert "function updateTwinStatusFromApp" in app
    assert "const liveStatus = {...s, frame_stale: frameStale};" in app
    assert "updateTwinStatusFromApp(liveStatus)" in app
    assert "id=\"twin-2d-fallback\"" in (ROOT / "frontend/index.html").read_text(encoding="utf-8")
    assert "twin-2d-fallback" in twin


def test_camera_null_fps_is_not_rendered_as_zero():
    app = (ROOT / "frontend/app.js").read_text(encoding="utf-8")
    assert "camera.fps != null && Number.isFinite(Number(camera.fps))" in app


def test_offline_analytics_has_native_fallback():
    analytics = (ROOT / "frontend/warehouse-analytics.js").read_text(encoding="utf-8")
    assert "analytics-fallback-bars" in analytics
    assert "window.KhoAIAnalytics={update(stats={})" in analytics


def test_blocking_alert_and_prompt_calls_are_removed():
    app = (ROOT / "frontend/app.js").read_text(encoding="utf-8")
    assert "window.alert(" not in app
    assert "window.prompt(" not in app
    assert "function toast(" in app
    assert "function confirmAction(" in app


def test_admin_tab_is_separate_and_history_filters_do_not_duplicate_system_logs():
    html = (ROOT / "frontend/index.html").read_text(encoding="utf-8")
    assert 'data-t="admin"' in html
    assert '<option value="system">Truy cập hệ thống</option>' not in html


def test_markup_ids_are_unique_and_all_table_headers_have_scope():
    parser = MarkupAudit()
    parser.feed((ROOT / "frontend/index.html").read_text(encoding="utf-8"))
    duplicates = [key for key, count in Counter(parser.ids).items() if count > 1]
    assert not duplicates
    assert parser.headers
    assert all(header.get("scope") == "col" for header in parser.headers)
    assert {"overview", "inside", "outside", "alerts", "history", "admin", "cards"}.issubset(set(parser.tabs))


def test_font_stack_has_system_fallback():
    css = (ROOT / "frontend/style.css").read_text(encoding="utf-8")
    assert '--font-ui:system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif' in css
    assert 'font-size:7px' not in css and 'font-size:8px' not in css and 'font-size:9px' not in css
    html = (ROOT / "frontend/index.html").read_text(encoding="utf-8")
    assert '<svg viewBox="0 0 24 24">' in html
    assert 'ĐIỀU HƯỚNG' in html


def test_role_is_resolved_on_initial_page_load_without_waiting_for_401():
    app = (ROOT / "frontend/app.js").read_text(encoding="utf-8")
    auth = (ROOT / "frontend/auth/auth-manager.js").read_text(encoding="utf-8")
    assert 'fetch("/api/auth/me", { credentials: "same-origin" })' in auth
    assert "requestAdminToken().then(user=>{if(user)applyRole(user);refresh();})" in app


def test_global_incident_count_uses_open_incidents_not_open_alerts():
    app = (ROOT / "frontend/app.js").read_text(encoding="utf-8")
    assert 'incidents.filter(item=>item.status==="OPEN").length' in app
    assert 'updateGlobalStatus(s, incidents)' in app


def test_esp32_heartbeat_is_updated_outside_three_module():
    app = (ROOT / "frontend/app.js").read_text(encoding="utf-8")
    assert 'const espStatus=document.getElementById("twin-esp-status")' in app
    assert 'espStatus.textContent=s.device_online?"Trực tuyến":"Ngoại tuyến"' in app


def test_2d_fallback_matches_four_rooms_cross_aisles_and_external_area():
    html = (ROOT / "frontend/index.html").read_text(encoding="utf-8")
    twin = (ROOT / "frontend/warehouse-twin.js").read_text(encoding="utf-8")
    css = (ROOT / "frontend/style.css").read_text(encoding="utf-8")
    assert 'class="warehouse-map-2d"' in html
    assert 'PHÒNG A' in html and 'PHÒNG B' in html and 'PHÒNG C' in html and 'PHÒNG D' in html
    assert 'LỐI VÀO CHÍNH' in html and 'KHU VỰC BÊN NGOÀI' in html
    assert 'Mô hình 3D hiện không khả dụng. Đang hiển thị sơ đồ kho 2D dự phòng.' in twin
    assert 'Kiểm tra kết nối/CDN' not in twin
    assert '.warehouse-map-2d .map-aisle' in css


def test_unchanged_live_lists_are_not_replaced_during_polling():
    app = (ROOT / "frontend/app.js").read_text(encoding="utf-8")
    assert 'function setHtmlIfChanged(element, html)' in app
    assert 'setHtmlIfChanged($("#alert-list"), alertHtml)' in app
    assert 'toast("Đã đánh dấu cảnh báo là đã xử lý.","success")' in app



def test_mobile_layout_rules_survive_header_css_consolidation():
    css = (ROOT / "frontend/style.css").read_text(encoding="utf-8")
    assert "@media(max-width:720px)" in css
    assert ".app-shell{display:block" in css
    assert ".sidebar{" in css and "overflow-x:auto" in css
    assert "@media(max-width:620px)" in css
    assert ".history-tabs{overflow-x:auto" in css
    assert ".history-tab{flex:0 0 auto;white-space:nowrap}" in css
    assert "@media(max-width:420px)" in css
    assert ".welcome-panel h1{font-size:" in css
    assert ".brand-copy small{font-size:" in css
    assert "Vuốt để xem" in css


def test_mobile_content_rules_are_complete_and_header_does_not_overlap_sticky_nav():
    css = (ROOT / "frontend/style.css").read_text(encoding="utf-8")
    mobile = css[css.find("/* Mobile layout completion"):]
    required = (
        "table{display:block", "overflow-x:auto", ".stats{grid-template-columns:repeat(2,minmax(0,1fr))",
        ".workspace{padding:20px 16px 44px", ".welcome-panel{padding:26px 24px",
        ".welcome-visual{right:3%", ".row label{flex:1 1 100%", ".cam{aspect-ratio:4/3",
        ".fallback-warehouse{height:210px}",
    )
    for rule in required:
        assert rule in mobile, f"Missing responsive rule: {rule}"
    mobile_header = css[css.find("@media(max-width:720px){.topbar"):]
    assert ".topbar{position:relative;top:auto" in mobile_header
    assert "flex:0 0 100%;width:100%;min-width:0" in mobile_header
    assert ".sidebar{\n    position:sticky;top:0" in css


def test_mobile_tables_and_stats_have_no_intrinsic_width_overflow():
    css = (ROOT / "frontend/style.css").read_text(encoding="utf-8")
    assert "table{display:block;width:100%;max-width:100%;overflow-x:auto;white-space:nowrap}" in css
    assert ".stats{grid-template-columns:repeat(2,minmax(0,1fr));gap:9px}" in css
    assert ".stats>.stat{min-width:0}" in css


def test_twin_legend_and_interaction_footer_use_separate_vertical_bands():
    css = (ROOT / "frontend/style.css").read_text(encoding="utf-8")
    assert ".twin-legend{position:absolute;left:12px;right:auto;bottom:74px" in css
    assert ".twin-stage-bottom{bottom:8px;left:12px;right:12px;display:grid" in css
    assert "max-width:calc(100% - 24px)" in css


def test_2d_fallback_is_runtime_activated_when_three_import_fails():
    html = (ROOT / "frontend/index.html").read_text(encoding="utf-8")
    twin = (ROOT / "frontend/warehouse-twin.js").read_text(encoding="utf-8")
    assert 'id="twin-2d-fallback" hidden' in html
    assert "await import('https://cdn.jsdelivr.net/npm/three@0.170.0/build/three.module.js')" in twin
    assert "const map2d=stage.querySelector('#twin-2d-fallback'); if(map2d) map2d.hidden=false" in twin


def test_decision_engine_documents_raw_inside_as_exceptional_fallback():
    decision = (ROOT / "ai/decision.py").read_text(encoding="utf-8")
    assert "normally after KHOAI_ENTER_CONFIRM_SECONDS, default 0.10 s" in decision
    assert "In the normal detector pipeline, `inside`" in decision
    assert "branch is intentionally exceptional" in decision


def test_twin_rooms_and_restricted_zone_are_interactive_without_fake_track_positions():
    twin = (ROOT / "frontend/warehouse-twin.js").read_text(encoding="utf-8")
    css = (ROOT / "frontend/style.css").read_text(encoding="utf-8")
    assert "interactiveTargets.push(roomMesh)" in twin
    assert "interactiveTargets.push(zoneFloor)" in twin
    assert "raycaster.intersectObjects(interactiveTargets,false)" in twin
    assert "không có dữ liệu định vị người/Track riêng cho phòng này" in twin
    assert "không biểu diễn tọa độ người thực tế" in twin
    assert ".twin-inspector[hidden]{display:none!important}" in css


def test_alarm_escalation_is_visually_distinct_on_3d_restricted_zone():
    twin = (ROOT / "frontend/warehouse-twin.js").read_text(encoding="utf-8")
    assert "lastState==='ALARM'?.48+Math.abs(Math.sin(t*4))*.48" in twin
    assert "zoneFloor.material.emissiveIntensity=.18+Math.abs(Math.sin(t*4))*.42" in twin
    assert "zoneEdges.material.color.set(color)" in twin
