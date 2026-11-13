from contextlib import contextmanager
from datetime import timezone
from types import SimpleNamespace

from backend.app.schemas import SecurityEventInput
from backend.app.services.external_event_processor import process_external_camera_event


class _DB:
    def __init__(self):
        self.calls = []

    def execute(self, sql, params=()):
        self.calls.append((sql, params))
        return self

    def fetchone(self):
        return (0,)


class _State:
    def __init__(self):
        self.outside = None
        self.inside = None

    def update_outside(self, people, seconds, ts):
        self.outside = (people, seconds, ts)

    def update_inside(self, view):
        self.inside = view


def _services():
    db = _DB()

    @contextmanager
    def db_session():
        yield db

    return SimpleNamespace(
        scans_recently_allowed=lambda _window: 1,
        external_camera_state=_State(),
        now_business=lambda: "2026-11-12T10:00:00+07:00",
        external_time_scale=1.0,
        external_warn_minutes=1.0,
        external_severe_minutes=5.0,
        db_session=db_session,
        business_tz=timezone.utc,
        current_alarm_level=lambda: "WARNING",
    ), db


def test_outside_event_updates_state_and_flags_possible_tailgating():
    services, _ = _services()
    alerts = []
    result = process_external_camera_event(
        SecurityEventInput(camera="outside", people_in_zone=2, max_seconds=10),
        services,
        lambda *args, **kwargs: alerts.append((args, kwargs)),
    )
    assert services.external_camera_state.outside == (
        2, 10, "2026-11-12T10:00:00+07:00"
    )
    assert [item[0][1] for item in alerts] == ["possible_tailgating"]
    assert result == {"ok": True, "alarm": "WARNING", "recorded": True}


def test_generic_event_is_persisted_with_safe_severity_fallback():
    services, db = _services()
    result = process_external_camera_event(
        SecurityEventInput(camera="external", event_type="custom", severity="invalid", message="hello"),
        services,
        lambda *args, **kwargs: None,
    )
    inserts = [call for call in db.calls if "INSERT INTO security_events" in call[0]]
    assert len(inserts) == 1
    assert inserts[0][1][1:5] == ("custom", None, "warning", "hello")
    assert result == {"ok": True, "alarm": "WARNING", "recorded": True}
