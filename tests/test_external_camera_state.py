from backend.app.services.external_camera_state import ExternalCameraState


def test_external_camera_state_initial_shape_and_legacy_mapping():
    store = ExternalCameraState()
    assert store.data == {
        "outside": {"people": 0, "max_seconds": 0, "ts": None},
        "inside": [],
    }
    store.data["inside"].append({"color": "red"})
    assert store.snapshot()["inside"] == [{"color": "red"}]


def test_external_camera_state_updates_and_snapshot_is_detached():
    store = ExternalCameraState()
    store.update_outside(2, 12.5, "2026-11-12T04:00:00+07:00")
    store.update_inside([{"color": "blue", "wrong": False}])

    snapshot = store.snapshot()
    assert snapshot["outside"] == {
        "people": 2, "max_seconds": 12.5, "ts": "2026-11-12T04:00:00+07:00"
    }
    snapshot["inside"].clear()
    assert store.snapshot()["inside"] == [{"color": "blue", "wrong": False}]
