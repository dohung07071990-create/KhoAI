from backend.app.services.incident_lifecycle import IncidentLifecycleService


class FakeDB:
    def __init__(self, rows=None):
        self.rows = list(rows or [])
        self.calls = []
    def execute(self, sql, params=()):
        self.calls.append((" ".join(sql.split()), params))
        row = self.rows.pop(0) if self.rows else None
        class Result:
            def __init__(self, value): self.value = value
            def fetchone(self): return self.value
        return Result(row)


def test_close_resolved_requires_safe_detector_state():
    db = FakeDB()
    service = IncidentLifecycleService(lambda: "2026-11-12T05:00:00", 3, 60, lambda: "ALARM")
    service.close_resolved(db)
    assert db.calls == []


def test_close_resolved_closes_only_acknowledged_open_intrusions_when_safe():
    db = FakeDB()
    service = IncidentLifecycleService(lambda: "2026-11-12T05:00:00", 3, 60, lambda: "SAFE")
    service.close_resolved(db)
    assert len(db.calls) == 1
    sql, params = db.calls[0]
    assert "status='CLOSED'" in sql
    assert "incident_type='intrusion'" in sql
    assert "acknowledged=1" in sql
    assert params == ("2026-11-12T05:00:00", "2026-11-12T05:00:00")
