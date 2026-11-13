import json


def test_expired_evidence_metadata_is_cleared_from_events_and_incident_history(tmp_path, monkeypatch):
    from backend.app import main

    monkeypatch.setattr(main, "DB_PATH", tmp_path / "test.sqlite3")
    main.init_db()
    details = {"evidence_url": "/api/camera/evidence/abc123.jpg", "track_id": 7}
    with main.db_session() as db:
        db.execute("""INSERT INTO security_events(event_at,event_type,track_id,severity,message,details_json,source_event_id)
            VALUES(?,?,?,?,?,?,?)""", ("2026-11-06T00:00:00+07:00", "unauthorized_entry", 7,
            "severe", "test", json.dumps(details), "source-1"))
        db.execute("""INSERT INTO incidents(incident_id,incident_type,started_at,updated_at,status,siren_until)
            VALUES(?,?,?,?,?,?)""", ("incident-1", "intrusion", "now", "now", "CLOSED", 0))
        db.execute("""INSERT INTO incident_events(incident_id,source_event_id,event_type,track_id,event_at,details_json)
            VALUES(?,?,?,?,?,?)""", ("incident-1", "source-1", "unauthorized_entry", 7,
            "2026-11-06T00:00:00+07:00", json.dumps(details)))

    assert main._mark_evidence_expired("abc123.jpg") == 2
    with main.db_session() as db:
        rows = db.execute("SELECT details_json FROM security_events UNION ALL SELECT details_json FROM incident_events").fetchall()
    for row in rows:
        updated = json.loads(row["details_json"])
        assert updated["evidence_url"] is None
        assert updated["evidence_expired"] is True
        assert updated["evidence_filename"] == "abc123.jpg"
        assert updated["evidence_status"] == "expired"
        assert updated["evidence_expired_at"]


def test_pruning_deleted_image_marks_event_reference_expired(tmp_path, monkeypatch):
    import os
    from backend.app import main

    monkeypatch.setattr(main, "DB_PATH", tmp_path / "retention.sqlite3")
    monkeypatch.setenv("KHOAI_EVIDENCE_MAX_AGE_DAYS", "1")
    main.init_db()
    evidence_dir = tmp_path / "evidence"
    evidence_dir.mkdir()
    image_path = evidence_dir / "expired001.jpg"
    image_path.write_bytes(b"old-image")
    old_time = main.time.time() - 3 * 86400
    os.utime(image_path, (old_time, old_time))
    details = {"evidence_url": "/api/camera/evidence/expired001.jpg", "evidence_filename": "expired001.jpg"}
    with main.db_session() as db:
        db.execute("""INSERT INTO security_events(event_at,event_type,severity,message,details_json,source_event_id)
            VALUES(?,?,?,?,?,?)""", ("2026-11-06T00:00:00+07:00", "zone_warning", "warning",
            "test", json.dumps(details), "expired-source"))

    assert main.prune_evidence_files(evidence_dir) == 1
    assert not image_path.exists()
    with main.db_session() as db:
        row = db.execute("SELECT details_json FROM security_events WHERE source_event_id='expired-source'").fetchone()
    updated = json.loads(row["details_json"])
    assert updated["evidence_url"] is None
    assert updated["evidence_expired"] is True
    assert updated["evidence_filename"] == "expired001.jpg"
    assert updated["evidence_status"] == "expired"
