from contextlib import contextmanager

from backend.app.services.device_read_service import DeviceReadService


class _DB:
    def __init__(self, rows=(), denied=None, unknown=None):
        self.rows = rows
        self.denied = denied
        self.unknown = unknown
        self.calls = []

    def execute(self, sql, params=()):
        self.calls.append((sql, params))
        if "FROM access_logs" in sql and "result='deny'" in sql:
            self.result = self.unknown
        elif "FROM access_logs" in sql:
            self.result = self.rows
        elif "FROM security_events" in sql:
            self.result = self.denied
        else:
            self.result = None
        return self

    def fetchall(self):
        return self.result or []

    def fetchone(self):
        return self.result


def _service(db):
    @contextmanager
    def session():
        yield db
    return DeviceReadService(session, lambda uid: f"masked:{uid}",
                             lambda rows: [{**row, "uid": f"masked:{row['uid']}"} for row in rows])


def test_list_scans_preserves_legacy_shape_and_masks_non_admin_uid():
    db = _DB(rows=[{"id": 3, "uid": "AB12", "card_name": "A", "event_at": "now", "result": "allow"}])
    rows = _service(db).list_scans(25, is_admin=False)
    assert rows == [{"id": 3, "uid": "masked:AB12", "result": "allow", "ts": "now", "name": "A", "reason": None}]
    assert db.calls[0][1] == (25,)


def test_list_scans_admin_keeps_uid_and_resolves_denial_reason():
    db = _DB(rows=[{"id": 4, "uid": "CD34", "card_name": "B", "event_at": "then", "result": "deny"}],
             denied={"details_json": '{"reason":"unknown_card"}'})
    rows = _service(db).list_scans(10, is_admin=True)
    assert rows[0]["uid"] == "CD34"
    assert rows[0]["reason"] == "unknown_card"


def test_last_unknown_card_masks_non_admin_and_handles_empty_database():
    db = _DB(unknown={"uid": "EF56", "event_at": "later"})
    assert _service(db).last_unknown_card(False) == {"uid": "masked:EF56", "ts": "later"}
    empty = _DB(unknown=None)
    assert _service(empty).last_unknown_card(True) == {"uid": None, "ts": None}
