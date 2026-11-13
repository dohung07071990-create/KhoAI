from contextlib import contextmanager

from backend.app.services.incident_reconciliation import IncidentReconciliationService


class FakeDetector:
    def __init__(self, enabled=True, raises=False):
        self.enabled = enabled
        self.raises = raises

    def status(self):
        if self.raises:
            raise RuntimeError("detector unavailable")
        return {"anti_theft_enabled": self.enabled}


def build_service(state="SAFE", detector=None):
    calls = {"db": 0, "close": 0}

    @contextmanager
    def db_session():
        calls["db"] += 1
        yield object()

    def close(_db):
        calls["close"] += 1

    service = IncidentReconciliationService(
        db_session=db_session,
        detector_state=lambda: state,
        detector_provider=lambda: detector or FakeDetector(),
        close_incident_if_resolved=close,
    )
    return service, calls


def test_reconciles_only_when_safe_and_anti_theft_enabled():
    service, calls = build_service()
    service.reconcile_open_incidents()
    assert calls == {"db": 1, "close": 1}


def test_does_not_open_database_when_detector_state_is_not_safe():
    service, calls = build_service(state="ALARM")
    service.reconcile_open_incidents()
    assert calls == {"db": 0, "close": 0}


def test_does_not_close_when_anti_theft_is_disabled():
    service, calls = build_service(detector=FakeDetector(enabled=False))
    service.reconcile_open_incidents()
    assert calls == {"db": 0, "close": 0}


def test_detector_failure_fails_closed():
    service, calls = build_service(detector=FakeDetector(raises=True))
    service.reconcile_open_incidents()
    assert calls == {"db": 0, "close": 0}


def test_detector_provider_failure_fails_closed():
    service, calls = build_service()

    def unavailable():
        raise RuntimeError("detector import failed")

    service.detector_provider = unavailable
    service.reconcile_open_incidents()
    assert calls == {"db": 0, "close": 0}
