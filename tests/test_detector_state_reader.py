from backend.app.services.detector_state import DetectorStateReader


class FakeDetector:
    def __init__(self, status):
        self._status = status

    def status(self):
        return self._status


def test_detector_state_is_normalized_to_uppercase():
    reader = DetectorStateReader(lambda: FakeDetector({"alarm_state": "warning"}))
    assert reader.get_state() == "WARNING"


def test_disabled_anti_theft_reports_disarmed():
    reader = DetectorStateReader(
        lambda: FakeDetector({"anti_theft_enabled": False, "alarm_state": "alarm"})
    )
    assert reader.get_state() == "DISARMED"


def test_missing_alarm_state_defaults_to_unknown():
    reader = DetectorStateReader(lambda: FakeDetector({}))
    assert reader.get_state() == "UNKNOWN"


def test_detector_provider_failure_fails_closed_to_unknown():
    def unavailable():
        raise RuntimeError("detector unavailable")

    reader = DetectorStateReader(unavailable)
    assert reader.get_state() == "UNKNOWN"
