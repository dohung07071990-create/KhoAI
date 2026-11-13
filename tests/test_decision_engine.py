"""Deterministic tests for the pure security decision engine."""
import pytest

from ai.decision import DecisionConfig, DecisionEngine


def test_unknown_person_has_grace_then_alarm():
    engine = DecisionEngine(DecisionConfig(entry_grace_seconds=15))
    first = engine.evaluate([{"track_id": 1, "zone_id": "zone_a", "inside": True}], armed=True, now=100.0)
    assert first.alarm_state == "WARNING"
    assert first.tracks["1"]["reason"] == "authorization_pending"
    second = engine.evaluate([{"track_id": 1, "zone_id": "zone_a", "inside": True}], armed=True, now=114.9)
    assert second.alarm_state == "WARNING"
    third = engine.evaluate([{"track_id": 1, "zone_id": "zone_a", "inside": True}], armed=True, now=115.0)
    assert third.alarm_state == "ALARM"
    assert any(event["type"] == "unauthorized_entry" for event in third.events)


def test_authorized_zone_suppresses_intrusion_alarm():
    engine = DecisionEngine()
    result = engine.evaluate([{"track_id": 7, "zone_id": "zone_a", "inside": True,
                               "authorized_zones": ["zone_a"]}], armed=True, now=10.0)
    assert result.alarm_state == "SAFE"
    assert result.tracks["7"]["state"] == "AUTHORIZED"


def test_authorized_card_wrong_zone_escalates():
    engine = DecisionEngine(DecisionConfig(wrong_zone_grace_seconds=5))
    obs = {"track_id": 3, "zone_id": "zone_b", "inside": True,
           "authorized_zones": ["zone_a"]}
    assert engine.evaluate([obs], armed=True, now=0).alarm_state == "WARNING"
    assert engine.evaluate([obs], armed=True, now=4.9).alarm_state == "WARNING"
    assert engine.evaluate([obs], armed=True, now=5).alarm_state == "ALARM"


def test_authorized_dwell_and_behavior_go_to_review_not_alarm():
    engine = DecisionEngine(DecisionConfig(dwell_review_seconds=30))
    obs = {"track_id": 4, "zone_id": "zone_a", "inside": True,
           "authorized_zones": ["zone_a"], "dwell_seconds": 31}
    result = engine.evaluate([obs], armed=True, now=40)
    assert result.alarm_state == "SAFE"
    assert result.tracks["4"]["state"] == "REVIEW"
    assert any(event["type"] == "review_required" for event in result.events)


def test_anonymous_detection_is_debounced_and_disarm_clears_live_alarm():
    engine = DecisionEngine(DecisionConfig(anonymous_debounce_seconds=1.0))
    assert engine.evaluate([], armed=True, now=1, anonymous_inside=True).alarm_state == "SAFE"
    alarm = engine.evaluate([], armed=True, now=2, anonymous_inside=True)
    assert alarm.alarm_state == "ALARM"
    assert sum(event["type"] == "anonymous_zone_alarm" for event in alarm.events) == 1
    repeated = engine.evaluate([], armed=True, now=3, anonymous_inside=True)
    assert repeated.alarm_state == "ALARM"
    assert not any(event["type"] == "anonymous_zone_alarm" for event in repeated.events)
    assert engine.evaluate([], armed=False, now=4).alarm_state == "SAFE"


def test_track_alarm_is_retained_during_short_missed_detection():
    engine = DecisionEngine(DecisionConfig(entry_grace_seconds=0, track_hold_seconds=5))
    obs = {"track_id": 21, "zone_id": "zone_a", "inside": True}
    assert engine.evaluate([obs], armed=True, now=0).alarm_state == "ALARM"
    assert engine.evaluate([], armed=True, now=1).alarm_state == "ALARM"
    assert engine.evaluate([], armed=True, now=4.9).alarm_state == "ALARM"
    assert engine.evaluate([], armed=True, now=5.1).alarm_state == "SAFE"


def test_presence_clock_accumulates_across_short_empty_gaps():
    engine = DecisionEngine(DecisionConfig(entry_grace_seconds=15, presence_release_seconds=30))
    obs = {"track_id": 31, "zone_id": "zone_a", "inside": True}
    assert engine.evaluate([obs], armed=True, now=0).alarm_state == "WARNING"
    assert engine.evaluate([obs], armed=True, now=10).alarm_state == "WARNING"
    engine.evaluate([], armed=True, now=10.5)
    assert engine.evaluate([obs], armed=True, now=10.5).alarm_state == "WARNING"
    assert engine.evaluate([obs], armed=True, now=15.5).alarm_state == "ALARM"


def test_new_track_does_not_inherit_old_track_authorization():
    engine = DecisionEngine()
    engine.evaluate([{"track_id": 10, "zone_id": "zone_a", "inside": True,
                      "authorized_zones": ["zone_a"]}], armed=True, now=0)
    result = engine.evaluate([{"track_id": 11, "zone_id": "zone_a", "inside": True}], armed=True, now=1)
    assert result.tracks["11"]["authorized"] is False
    assert result.tracks["11"]["state"] == "WARNING"


def test_arming_with_existing_unauthorized_occupant_is_immediate_alarm():
    engine = DecisionEngine(DecisionConfig(entry_grace_seconds=15))
    engine.evaluate([{"track_id": 2, "zone_id": "zone_a", "inside": True}], armed=False, now=100)
    result = engine.evaluate([{"track_id": 2, "zone_id": "zone_a", "inside": True,
                               "immediate_alarm": True}], armed=True, now=101)
    assert result.alarm_state == "ALARM"


def test_anonymous_exit_is_held_for_track_hold_window():
    engine = DecisionEngine(DecisionConfig(anonymous_debounce_seconds=0, track_hold_seconds=5))
    assert engine.evaluate([], armed=True, now=0, anonymous_inside=True).alarm_state == "ALARM"
    assert engine.evaluate([], armed=True, now=1, anonymous_inside=False).alarm_state == "ALARM"
    assert engine.evaluate([], armed=True, now=5.9, anonymous_inside=False).alarm_state == "ALARM"
    assert engine.evaluate([], armed=True, now=6.1, anonymous_inside=False).alarm_state == "SAFE"


def test_authorizing_last_unauthorized_person_resets_zone_clock_immediately():
    engine = DecisionEngine(DecisionConfig(entry_grace_seconds=15, presence_release_seconds=30))
    unauthed = {"track_id": 41, "zone_id": "zone_a", "inside": True}
    engine.evaluate([unauthed], armed=True, now=0)
    engine.evaluate([unauthed], armed=True, now=10)
    authorized = {"track_id": 41, "zone_id": "zone_a", "inside": True,
                  "authorized_zones": ["zone_a"]}
    engine.evaluate([authorized], armed=True, now=10.5)
    second_person = {"track_id": 42, "zone_id": "zone_a", "inside": True}
    result = engine.evaluate([authorized, second_person], armed=True, now=11)
    assert result.tracks["42"]["state"] == "WARNING"


def test_single_missed_frame_does_not_drop_alarm_or_emit_state_change():
    engine = DecisionEngine(DecisionConfig(entry_grace_seconds=0, track_hold_seconds=5))
    obs = {"track_id": 51, "zone_id": "zone_a", "inside": True}
    first = engine.evaluate([obs], armed=True, now=0)
    assert first.alarm_state == "ALARM"
    missed = engine.evaluate([], armed=True, now=0.1)
    assert missed.alarm_state == "ALARM"
    assert not any(event["type"] == "alarm_state_changed" for event in missed.events)


def test_sequential_tracks_do_not_share_entry_grace():
    engine = DecisionEngine(DecisionConfig(entry_grace_seconds=8))
    # Four distinct tracks each occupy the zone for six seconds, with gaps.
    for track_id, start in enumerate((0, 16, 32, 48), start=100):
        engine.evaluate([{"track_id": track_id, "zone_id": "zone_a", "inside": True}],
                        armed=True, now=float(start))
        result = engine.evaluate([{"track_id": track_id, "zone_id": "zone_a", "inside": True}],
                                 armed=True, now=float(start + 6))
        assert result.alarm_state == "WARNING"
    assert result.alarm_state != "ALARM"


def test_brief_buffer_contact_is_passerby_without_event():
    engine = DecisionEngine(DecisionConfig(passerby_confirm_seconds=3))
    obs = {"track_id": 90, "zone_id": "zone_a", "inside": False, "warning": True}
    first = engine.evaluate([obs], armed=True, now=0)
    assert first.tracks["90"]["state"] == "PASSERBY"
    assert not any(event["type"] == "zone_warning" for event in first.events)
    confirmed = engine.evaluate([obs], armed=True, now=3)
    assert confirmed.tracks["90"]["state"] == "WARNING"
    assert any(event["type"] == "zone_warning" for event in confirmed.events)


def test_short_unauthorized_intrusion_exit_emits_event_only_after_session_release():
    engine = DecisionEngine(DecisionConfig(entry_grace_seconds=15, presence_release_seconds=1.0,
                                           exit_hysteresis_seconds=0.5))
    obs = {"track_id": 91, "zone_id": "zone_a", "inside": True}
    engine.evaluate([obs], armed=True, now=0)
    engine.evaluate([obs], armed=True, now=6)
    engine.evaluate([{"track_id": 91, "zone_id": "zone_a", "inside": False}], armed=True, now=6.1)
    pending = engine.evaluate([{"track_id": 91, "zone_id": "zone_a", "inside": False}], armed=True, now=6.7)
    assert pending.tracks["91"]["session_id"] is not None
    assert not any(event["type"] == "intrusion_attempt_aborted" for event in pending.events)
    result = engine.evaluate([{"track_id": 91, "zone_id": "zone_a", "inside": False}], armed=True, now=7.8)
    event = next(event for event in result.events if event["type"] == "intrusion_attempt_aborted")
    assert event["duration_seconds"] >= 5
    assert event["severity"] == "warning"
    assert result.tracks["91"]["session_id"] is None



def test_realistic_one_second_edge_flicker_keeps_one_session_and_emits_one_close_event():
    engine = DecisionEngine(DecisionConfig(entry_grace_seconds=30.0,
                                           exit_hysteresis_seconds=0.5,
                                           presence_release_seconds=8.0))
    events = []
    session_ids = set()
    inside = {"track_id": 301, "zone_id": "zone_a", "inside": True}
    outside = {"track_id": 301, "zone_id": "zone_a", "inside": False,
                "exit_boundary_inside": False}
    first = engine.evaluate([inside], armed=True, now=0.0)
    session_ids.add(first.tracks["301"]["session_id"])
    events.extend(first.events)
    # Ten cycles: about one second inside, one second outside, with a 0.5 s
    # engine exit confirmation. Every re-entry occurs before the 8 s release.
    for i in range(10):
        base = 1.0 + i * 2.5
        for obs, at in ((inside, base), (outside, base + 1.0), (outside, base + 1.5)):
            result = engine.evaluate([obs], armed=True, now=at)
            events.extend(result.events)
            session_ids.add(result.tracks["301"]["session_id"])
        # Re-entry on the next cycle is one second after confirmed exit.
    assert len(session_ids) == 1
    assert sum(e["type"] == "intrusion_attempt_aborted" for e in events) == 0
    # The final release closes the one long-lived session once.
    closed = engine.evaluate([outside], armed=True, now=1.0 + 9 * 2.5 + 1.5 + 8.1)
    events.extend(closed.events)
    assert sum(e["type"] == "intrusion_attempt_aborted" for e in events) == 1
    assert closed.tracks["301"]["session_id"] is None



def test_alarm_remains_latched_until_presence_release_finishes():
    engine = DecisionEngine(DecisionConfig(entry_grace_seconds=1.0,
                                           exit_hysteresis_seconds=0.5,
                                           presence_release_seconds=8.0))
    inside = {"track_id": 304, "zone_id": "zone_a", "inside": True}
    outside = {"track_id": 304, "zone_id": "zone_a", "inside": False,
               "exit_boundary_inside": False}
    engine.evaluate([inside], armed=True, now=0.0)
    alarm = engine.evaluate([inside], armed=True, now=1.0)
    session_id = alarm.tracks["304"]["session_id"]
    assert alarm.alarm_state == "ALARM"
    engine.evaluate([outside], armed=True, now=1.1)
    pending = engine.evaluate([outside], armed=True, now=1.6)
    assert pending.alarm_state == "ALARM"
    assert pending.tracks["304"]["session_id"] == session_id
    still_pending = engine.evaluate([outside], armed=True, now=9.5)
    assert still_pending.alarm_state == "ALARM"
    released = engine.evaluate([outside], armed=True, now=9.7)
    assert released.alarm_state == "SAFE"
    assert released.tracks["304"]["session_id"] is None


def test_reentry_after_release_creates_new_session_only_after_old_one_closes():
    engine = DecisionEngine(DecisionConfig(entry_grace_seconds=30.0,
                                           exit_hysteresis_seconds=0.5,
                                           presence_release_seconds=2.0))
    inside = {"track_id": 305, "zone_id": "zone_a", "inside": True}
    outside = {"track_id": 305, "zone_id": "zone_a", "inside": False,
               "exit_boundary_inside": False}
    first = engine.evaluate([inside], armed=True, now=0.0)
    first_id = first.tracks["305"]["session_id"]
    engine.evaluate([inside], armed=True, now=5.0)
    engine.evaluate([outside], armed=True, now=5.1)
    pending = engine.evaluate([outside], armed=True, now=5.6)
    assert pending.tracks["305"]["session_id"] == first_id
    second = engine.evaluate([inside], armed=True, now=7.7)
    assert second.tracks["305"]["session_id"] != first_id
    assert any(e["type"] == "intrusion_attempt_aborted" for e in second.events)

def test_two_seconds_in_one_second_out_preserves_session_until_release():
    engine = DecisionEngine(DecisionConfig(entry_grace_seconds=30.0,
                                           exit_hysteresis_seconds=0.5,
                                           presence_release_seconds=8.0))
    inside = {"track_id": 302, "zone_id": "zone_a", "inside": True}
    outside = {"track_id": 302, "zone_id": "zone_a", "inside": False,
               "exit_boundary_inside": False}
    events = []
    first = engine.evaluate([inside], armed=True, now=0.0)
    session_id = first.tracks["302"]["session_id"]
    events.extend(first.events)
    for i in range(4):
        base = 1.0 + i * 3.5
        for obs, at in ((inside, base), (inside, base + 1.0),
                        (outside, base + 2.0), (outside, base + 2.5)):
            result = engine.evaluate([obs], armed=True, now=at)
            events.extend(result.events)
            assert result.tracks["302"]["session_id"] == session_id
    assert sum(e["type"] == "access_pending" for e in events) == 1
    assert sum(e["type"] == "intrusion_attempt_aborted" for e in events) == 0


def test_noisy_spatial_boundary_does_not_split_session_before_release():
    import random
    rng = random.Random(20261106)
    engine = DecisionEngine(DecisionConfig(entry_grace_seconds=40.0,
                                           exit_hysteresis_seconds=0.5,
                                           presence_release_seconds=8.0))
    session_ids = set()
    events = []
    now = 0.0
    for _ in range(120):
        # Jitter around the edge: most samples remain within the spatial exit
        # buffer; occasional samples cross it for short bursts.
        in_core = rng.random() < 0.55
        in_buffer = rng.random() < 0.82
        obs = {"track_id": 303, "zone_id": "zone_a",
               "inside": in_core, "exit_boundary_inside": in_buffer}
        result = engine.evaluate([obs], armed=True, now=now)
        events.extend(result.events)
        sid = result.tracks["303"]["session_id"]
        if sid:
            session_ids.add(sid)
        now += rng.uniform(0.08, 0.18)
    assert len(session_ids) <= 1
    assert sum(e["type"] == "intrusion_attempt_aborted" for e in events) == 0

def test_track_id_handover_keeps_same_person_entry_timer():
    engine = DecisionEngine(DecisionConfig(entry_grace_seconds=8, track_hold_seconds=5))
    old = {"track_id": 1, "zone_id": "zone_a", "inside": True, "position": [0.50, 0.60]}
    engine.evaluate([old], armed=True, now=0)
    engine.evaluate([old], armed=True, now=4)
    engine.evaluate([old], armed=True, now=7.9)
    new = {"track_id": 2, "zone_id": "zone_a", "inside": True, "position": [0.52, 0.60]}
    result = engine.evaluate([new], armed=True, now=8.1)
    assert result.tracks["2"]["state"] == "ALARM"


def test_ambiguous_track_handover_does_not_inherit_timer():
    engine = DecisionEngine(DecisionConfig(entry_grace_seconds=8, track_hold_seconds=5))
    old = {"track_id": 1, "zone_id": "zone_a", "inside": True, "position": [0.50, 0.60]}
    engine.evaluate([old], armed=True, now=0)
    engine.evaluate([old], armed=True, now=4)
    new_a = {"track_id": 2, "zone_id": "zone_a", "inside": True, "position": [0.51, 0.60]}
    new_b = {"track_id": 3, "zone_id": "zone_a", "inside": True, "position": [0.52, 0.60]}
    result = engine.evaluate([new_a, new_b], armed=True, now=5)
    assert result.tracks["2"]["state"] == "WARNING"
    assert result.tracks["3"]["state"] == "WARNING"


def test_alarmed_track_exit_does_not_emit_aborted_attempt():
    engine = DecisionEngine(DecisionConfig(entry_grace_seconds=5))
    obs = {"track_id": 9, "zone_id": "zone_a", "inside": True}
    engine.evaluate([obs], armed=True, now=0)
    alarmed = engine.evaluate([obs], armed=True, now=6)
    assert alarmed.tracks["9"]["state"] == "ALARM"
    exited = engine.evaluate([{"track_id": 9, "zone_id": "zone_a", "inside": False}], armed=True, now=7)
    assert not any(event["type"] == "intrusion_attempt_aborted" for event in exited.events)


def test_demo_decision_defaults_are_consistent_eight_seconds():
    config = DecisionConfig()
    assert config.entry_grace_seconds == 8
    assert config.wrong_zone_grace_seconds == 8
    assert config.presence_release_seconds == 8


def test_handover_does_not_inherit_after_long_track_gap():
    engine = DecisionEngine(DecisionConfig(entry_grace_seconds=8, handover_max_gap_seconds=4.25))
    old = {"track_id": 101, "zone_id": "zone_a", "inside": True, "position": [0.50, 0.60]}
    engine.evaluate([old], armed=True, now=0)
    engine.evaluate([old], armed=True, now=4)
    new = {"track_id": 102, "zone_id": "zone_a", "inside": True, "position": [0.51, 0.60]}
    result = engine.evaluate([new], armed=True, now=8.3)
    assert result.tracks["102"]["state"] == "WARNING"
    assert result.tracks["102"]["elapsed_seconds"] < 1


def test_handover_rejected_when_live_track_explains_old_position():
    engine = DecisionEngine(DecisionConfig(entry_grace_seconds=8, handover_max_gap_seconds=4.25))
    old = {"track_id": 201, "zone_id": "zone_a", "inside": True, "position": [0.50, 0.60]}
    other = {"track_id": 202, "zone_id": "zone_a", "inside": True, "position": [0.80, 0.60]}
    engine.evaluate([old, other], armed=True, now=0)
    # The existing second person moves to the old person's last position.
    other_at_old_position = {**other, "position": [0.50, 0.60]}
    engine.evaluate([other_at_old_position], armed=True, now=2)
    replacement = {"track_id": 203, "zone_id": "zone_a", "inside": True, "position": [0.51, 0.60]}
    result = engine.evaluate([other_at_old_position, replacement], armed=True, now=3)
    assert result.tracks["203"]["state"] == "WARNING"
    assert result.tracks["203"]["elapsed_seconds"] < 1


def test_exit_hysteresis_keeps_timer_running_and_does_not_drop_alarm_on_one_outside_frame():
    engine = DecisionEngine(DecisionConfig(entry_grace_seconds=2.0, exit_hysteresis_seconds=1.0))
    obs = {"track_id": 70, "zone_id": "zone_a", "inside": True}
    assert engine.evaluate([obs], armed=True, now=0.0).alarm_state == "WARNING"
    outside = {"track_id": 70, "zone_id": "zone_a", "inside": False,
               "exit_boundary_inside": False}
    # One outside frame starts the exit timer; the grace clock continues.
    assert engine.evaluate([outside], armed=True, now=1.0).alarm_state == "WARNING"
    # At the next frame the grace deadline is reached while exit is still being confirmed.
    result = engine.evaluate([outside], armed=True, now=2.0)
    assert result.alarm_state == "ALARM"
    assert any(e["type"] == "unauthorized_entry" for e in result.events)


def test_spatial_exit_buffer_cancels_exit_candidate_without_ending_session():
    engine = DecisionEngine(DecisionConfig(entry_grace_seconds=20.0, exit_hysteresis_seconds=0.5))
    inside = {"track_id": 71, "zone_id": "zone_a", "inside": True}
    edge = {"track_id": 71, "zone_id": "zone_a", "inside": False,
            "exit_boundary_inside": True}
    engine.evaluate([inside], armed=True, now=0.0)
    engine.evaluate([edge], armed=True, now=1.0)
    result = engine.evaluate([inside], armed=True, now=1.2)
    assert result.tracks["71"]["state"] == "WARNING"
    assert result.tracks["71"]["session_id"] is not None
    assert not any(e["type"] == "intrusion_attempt_aborted" for e in result.events)


def test_repeated_edge_flicker_does_not_emit_multiple_aborted_attempts():
    engine = DecisionEngine(DecisionConfig(entry_grace_seconds=30.0, exit_hysteresis_seconds=0.5))
    events = []
    for index in range(41):
        now = index * 0.25
        if index == 0 or index % 2 == 0:
            obs = [{"track_id": 72, "zone_id": "zone_a", "inside": True}]
        else:
            obs = [{"track_id": 72, "zone_id": "zone_a", "inside": False,
                    "exit_boundary_inside": False}]
        result = engine.evaluate(obs, armed=True, now=now)
        events.extend(result.events)
    assert sum(e["type"] == "intrusion_attempt_aborted" for e in events) == 0


def test_handover_never_transfers_timer_to_new_track_outside_zone():
    engine = DecisionEngine(DecisionConfig(entry_grace_seconds=8.0, handover_match_radius=0.1))
    engine.evaluate([{"track_id": 80, "zone_id": "zone_a", "inside": True,
                      "position": [0.5, 0.5]}], armed=True, now=0.0)
    result = engine.evaluate([{"track_id": 81, "zone_id": "zone_a", "inside": False,
                               "position": [0.51, 0.5]}], armed=True, now=1.0)
    assert result.tracks["81"]["elapsed_seconds"] == 0.0
    assert result.tracks["81"]["session_id"] is None


def test_session_id_survives_track_handover():
    engine = DecisionEngine(DecisionConfig(entry_grace_seconds=8.0, handover_match_radius=0.1,
                                           handover_exclusion_radius=0.03))
    first = engine.evaluate([{"track_id": 90, "zone_id": "zone_a", "inside": True,
                              "position": [0.5, 0.5]}], armed=True, now=0.0)
    session_id = first.tracks["90"]["session_id"]
    second = engine.evaluate([{"track_id": 91, "zone_id": "zone_a", "inside": True,
                               "position": [0.51, 0.5]}], armed=True, now=1.0)
    assert second.tracks["91"]["session_id"] == session_id


@pytest.mark.parametrize("gap_seconds", [5.0, 6.0, 8.0, 10.0])
def test_characterization_track_gap_beyond_handover_resets_timer(gap_seconds):
    """Characterization: identity continuity is not claimed after the short handover window."""
    engine = DecisionEngine(DecisionConfig(entry_grace_seconds=8.0, track_hold_seconds=5.0,
                                           handover_max_gap_seconds=4.25))
    engine.evaluate([{"track_id": 101, "zone_id": "zone_a", "inside": True,
                      "position": [0.4, 0.4]}], armed=True, now=0.0)
    result = engine.evaluate([{"track_id": 102, "zone_id": "zone_a", "inside": True,
                               "position": [0.4, 0.4]}], armed=True, now=gap_seconds)
    assert result.tracks["102"]["elapsed_seconds"] == 0.0
    assert result.tracks["102"]["session_id"] != None



def test_warning_hit_and_run_emits_aborted_when_track_is_deleted_before_release():
    engine = DecisionEngine(DecisionConfig(entry_grace_seconds=15.0,
                                           track_hold_seconds=5.0,
                                           exit_hysteresis_seconds=0.5,
                                           presence_release_seconds=8.0))
    inside = {"track_id": 701, "zone_id": "zone_a", "inside": True}
    outside = {"track_id": 701, "zone_id": "zone_a", "inside": False,
               "exit_boundary_inside": False}
    engine.evaluate([inside], armed=True, now=0.0)
    engine.evaluate([inside], armed=True, now=6.0)
    engine.evaluate([outside], armed=True, now=6.1)
    confirmed_exit = engine.evaluate([outside], armed=True, now=6.7)
    session_id = confirmed_exit.tracks["701"]["session_id"]
    assert session_id
    engine.evaluate([outside], armed=True, now=8.2)
    lost = engine.evaluate([], armed=True, now=13.3)
    aborted = [event for event in lost.events if event["type"] == "intrusion_attempt_aborted"]
    assert len(aborted) == 1
    assert aborted[0]["session_id"] == session_id
    assert aborted[0]["reason"] == "track_lost_before_presence_release"
    later = engine.evaluate([], armed=True, now=14.0)
    assert not any(event["type"] == "intrusion_attempt_aborted" for event in later.events)


def test_authorized_nearby_track_does_not_block_missing_intruder_handover():
    engine = DecisionEngine(DecisionConfig(entry_grace_seconds=8.0,
                                           handover_max_gap_seconds=1.0,
                                           handover_match_radius=0.1,
                                           handover_exclusion_radius=0.08))
    old = {"track_id": 711, "zone_id": "zone_a", "inside": True,
           "position": [0.50, 0.50]}
    engine.evaluate([old], armed=True, now=0.0)
    engine.evaluate([old], armed=True, now=3.0)
    employee = {"track_id": 712, "zone_id": "zone_a", "inside": True,
                "position": [0.53, 0.50], "authorized_zones": ["zone_a"]}
    engine.evaluate([employee], armed=True, now=3.5)
    replacement = {"track_id": 713, "zone_id": "zone_a", "inside": True,
                   "position": [0.51, 0.50]}
    result = engine.evaluate([employee, replacement], armed=True, now=4.0)
    assert result.tracks["713"]["session_id"] is not None
    assert result.tracks["713"]["state"] == "WARNING"


def test_two_second_gap_does_not_transfer_intrusion_timer_to_another_person():
    engine = DecisionEngine(DecisionConfig(entry_grace_seconds=8.0,
                                           handover_max_gap_seconds=1.0,
                                           handover_match_radius=0.1))
    first = {"track_id": 721, "zone_id": "zone_a", "inside": True,
             "position": [0.50, 0.50]}
    engine.evaluate([first], armed=True, now=0.0)
    engine.evaluate([first], armed=True, now=6.0)
    second = {"track_id": 722, "zone_id": "zone_a", "inside": True,
              "position": [0.50, 0.50]}
    result = engine.evaluate([second], armed=True, now=8.0)
    assert result.tracks["722"]["state"] == "WARNING"
    assert result.tracks["722"]["elapsed_seconds"] == 0.0


def test_prolonged_warning_zone_presence_escalates_to_suspicious_not_alarm():
    engine = DecisionEngine(DecisionConfig(passerby_confirm_seconds=3.0,
                                           suspicious_seconds=120.0))
    obs = {"track_id": 731, "zone_id": "zone_a", "inside": False, "warning": True}
    assert engine.evaluate([obs], armed=True, now=0.0).tracks["731"]["state"] == "PASSERBY"
    assert engine.evaluate([obs], armed=True, now=3.0).tracks["731"]["state"] == "WARNING"
    result = engine.evaluate([obs], armed=True, now=120.0)
    assert result.tracks["731"]["state"] == "SUSPICIOUS"
    assert result.alarm_state == "WARNING"
    assert any(event["type"] == "suspicious_presence" for event in result.events)


@pytest.mark.parametrize("gap", [0.4, 0.8, 1.0, 1.5, 2.0, 2.5, 3.0])
def test_id_handover_recovers_intruder_across_cpu_frame_gaps(gap):
    engine = DecisionEngine(DecisionConfig(entry_grace_seconds=8.0,
                                           handover_max_gap_seconds=3.5,
                                           handover_match_radius=0.08))
    old = {"track_id": 801, "zone_id": "zone_a", "inside": True,
           "position": (0.50, 0.60)}
    engine.evaluate([old], armed=True, now=0.0)
    engine.evaluate([old], armed=True, now=4.0)
    new = {"track_id": 802, "zone_id": "zone_a", "inside": True,
           "position": (0.505, 0.60)}
    resumed = engine.evaluate([new], armed=True, now=4.0 + gap)
    assert resumed.tracks["802"]["session_id"] is not None
    alarm = engine.evaluate([new], armed=True, now=8.0 + gap)
    assert alarm.alarm_state == "ALARM"
    assert any(e["type"] == "unauthorized_entry" and e["track_id"] == 802
               for e in alarm.events)


@pytest.mark.parametrize("gap", [1.0, 2.0, 3.0])
def test_track_leaving_at_frame_edge_does_not_transfer_timer_to_new_person(gap):
    engine = DecisionEngine(DecisionConfig(entry_grace_seconds=8.0,
                                           handover_max_gap_seconds=3.5,
                                           handover_match_radius=0.08))
    old = {"track_id": 811, "zone_id": "zone_a", "inside": True,
           "position": (0.50, 0.60), "exited_frame_edge": True}
    engine.evaluate([old], armed=True, now=0.0)
    engine.evaluate([old], armed=True, now=4.0)
    new = {"track_id": 812, "zone_id": "zone_a", "inside": True,
           "position": (0.50, 0.60), "exited_frame_edge": False}
    result = engine.evaluate([new], armed=True, now=4.0 + gap)
    assert result.tracks["812"]["state"] == "WARNING"
    assert result.tracks["812"]["elapsed_seconds"] == 0.0
    before_own_grace = engine.evaluate([new], armed=True, now=8.0 + gap)
    assert before_own_grace.alarm_state != "ALARM"
    own_alarm = engine.evaluate([new], armed=True, now=12.0 + gap)
    assert own_alarm.alarm_state == "ALARM"


def test_suspicious_after_thirty_seconds_of_buffer_presence():
    engine = DecisionEngine(DecisionConfig(suspicious_seconds=30.0))
    obs = {"track_id": 821, "zone_id": "zone_a", "inside": False, "warning": True}
    engine.evaluate([obs], armed=True, now=0.0)
    engine.evaluate([obs], armed=True, now=15.0)
    result = engine.evaluate([obs], armed=True, now=30.0)
    assert result.tracks["821"]["state"] == "SUSPICIOUS"
    assert any(e["type"] == "suspicious_presence" for e in result.events)


def test_suspicious_duration_pauses_for_short_buffer_exit():
    engine = DecisionEngine(DecisionConfig(suspicious_seconds=30.0, suspicious_gap_seconds=4.0))
    warning = {"track_id": 822, "zone_id": "zone_a", "inside": False, "warning": True}
    outside = {"track_id": 822, "zone_id": "zone_a", "inside": False, "warning": False}
    engine.evaluate([warning], armed=True, now=0.0)
    engine.evaluate([warning], armed=True, now=10.0)
    engine.evaluate([outside], armed=True, now=10.1)
    engine.evaluate([warning], armed=True, now=13.0)  # 2.9 s interruption
    result = engine.evaluate([warning], armed=True, now=33.0)
    assert result.tracks["822"]["state"] == "SUSPICIOUS"


def test_suspicious_duration_resets_after_gap_exceeds_four_seconds():
    engine = DecisionEngine(DecisionConfig(suspicious_seconds=30.0, suspicious_gap_seconds=4.0))
    warning = {"track_id": 823, "zone_id": "zone_a", "inside": False, "warning": True}
    outside = {"track_id": 823, "zone_id": "zone_a", "inside": False, "warning": False}
    engine.evaluate([warning], armed=True, now=0.0)
    engine.evaluate([warning], armed=True, now=10.0)
    engine.evaluate([outside], armed=True, now=10.1)
    result = engine.evaluate([warning], armed=True, now=15.2)  # 5.1 s interruption
    result = engine.evaluate([warning], armed=True, now=35.0)
    assert result.tracks["823"]["state"] != "SUSPICIOUS"


def test_three_qualified_approaches_trigger_suspicious():
    engine = DecisionEngine(DecisionConfig(suspicious_seconds=30.0,
                                           suspicious_gap_seconds=4.0,
                                           suspicious_approach_min_seconds=2.0,
                                           suspicious_approach_count=3,
                                           suspicious_approach_window_seconds=120.0))
    warning = {"track_id": 824, "zone_id": "zone_a", "inside": False, "warning": True}
    outside = {"track_id": 824, "zone_id": "zone_a", "inside": False, "warning": False}
    for start in (0.0, 10.0, 20.0):
        engine.evaluate([warning], armed=True, now=start)
        engine.evaluate([warning], armed=True, now=start + 2.0)
        result = engine.evaluate([warning], armed=True, now=start + 5.0)
        if start < 20.0:
            engine.evaluate([outside], armed=True, now=start + 5.1)
    assert result.tracks["824"]["state"] == "SUSPICIOUS"
    assert result.tracks["824"]["approach_count"] == 3


def test_four_short_passersby_do_not_trigger_suspicious():
    engine = DecisionEngine(DecisionConfig(suspicious_seconds=30.0,
                                           suspicious_approach_min_seconds=2.0,
                                           suspicious_approach_count=3))
    for track_id, start in enumerate((0.0, 10.0, 20.0, 30.0), start=830):
        obs = {"track_id": track_id, "zone_id": "zone_a", "inside": False, "warning": True}
        engine.evaluate([obs], armed=True, now=start)
        result = engine.evaluate([obs], armed=True, now=start + 1.5)
        assert result.tracks[str(track_id)]["state"] != "SUSPICIOUS"


def test_lost_track_aborted_event_has_numeric_id_and_two_timestamps():
    engine = DecisionEngine(DecisionConfig(entry_grace_seconds=15.0, track_hold_seconds=2.0))
    obs = {"track_id": 841, "zone_id": "zone_a", "inside": True}
    engine.evaluate([obs], armed=True, now=0.0)
    engine.evaluate([obs], armed=True, now=6.0)
    engine.evaluate([], armed=True, now=6.5)
    result = engine.evaluate([], armed=True, now=12.7)
    event = next(e for e in result.events if e["type"] == "intrusion_attempt_aborted")
    assert isinstance(event["track_id"], int)
    assert event["lost_at"] == 6.0
    assert event["emitted_at"] == 12.7
    assert event["emitted_at"] > event["lost_at"]


def test_stationary_near_edge_track_can_handover_and_alarm():
    engine = DecisionEngine(DecisionConfig(entry_grace_seconds=8.0, handover_max_gap_seconds=3.5))
    old = {"track_id": 901, "zone_id": "zone_a", "inside": True,
           "position": (0.02, 0.60), "exited_frame_edge": False}
    engine.evaluate([old], armed=True, now=0.0)
    engine.evaluate([old], armed=True, now=4.0)
    new = {"track_id": 902, "zone_id": "zone_a", "inside": True,
           "position": (0.021, 0.60), "exited_frame_edge": False}
    resumed = engine.evaluate([new], armed=True, now=5.0)
    assert resumed.tracks["902"]["elapsed_seconds"] >= 4.0
    result = engine.evaluate([new], armed=True, now=8.1)
    assert result.alarm_state == "ALARM"


def test_warning_buffer_handover_transfers_only_proximity_not_intrusion_session():
    engine = DecisionEngine(DecisionConfig(passerby_confirm_seconds=3.0, suspicious_seconds=30.0,
                                           suspicious_approach_count=99, entry_grace_seconds=1.0,
                                           handover_max_gap_seconds=3.5))
    old = {"track_id": 911, "zone_id": "zone_a", "inside": False, "warning": True,
           "position": (0.5, 0.5)}
    engine.evaluate([old], armed=True, now=0.0)
    engine.evaluate([old], armed=True, now=4.9)
    # The old ID starts an intrusion session; the replacement is only in the buffer.
    old_intruder = {"track_id": 911, "zone_id": "zone_a", "inside": True,
                    "position": (0.5, 0.5)}
    engine.evaluate([old_intruder], armed=True, now=5.0)
    new = {"track_id": 912, "zone_id": "zone_a", "inside": False, "warning": True,
           "position": (0.505, 0.5)}
    result = engine.evaluate([new], armed=True, now=5.1)
    assert result.tracks["912"]["state"] == "WARNING"
    assert result.tracks["912"]["elapsed_seconds"] == 0.0
    assert result.tracks["912"]["session_id"] is None


def test_warning_buffer_proximity_survives_repeated_id_changes_for_40_seconds():
    engine = DecisionEngine(DecisionConfig(passerby_confirm_seconds=3.0, suspicious_seconds=40.0,
                                           suspicious_gap_seconds=4.0, suspicious_approach_count=99,
                                           handover_max_gap_seconds=3.5, handover_match_radius=0.08))
    current_id = 1000
    position = (0.50, 0.50)
    engine.evaluate([{"track_id": current_id, "zone_id": "zone_a", "inside": False,
                      "warning": True, "position": position}], armed=True, now=0.0)
    for step in range(1, 9):
        old = {"track_id": current_id, "zone_id": "zone_a", "inside": False,
               "warning": True, "position": position}
        engine.evaluate([old], armed=True, now=step * 5.0 - 0.1)
        current_id += 1
        new = {"track_id": current_id, "zone_id": "zone_a", "inside": False,
               "warning": True, "position": position}
        result = engine.evaluate([new], armed=True, now=step * 5.0)
    assert result.tracks[str(current_id)]["state"] == "SUSPICIOUS"
    assert result.tracks[str(current_id)]["proximity_seconds"] >= 40.0


def test_four_separate_buffer_passers_do_not_accumulate_proximity():
    engine = DecisionEngine(DecisionConfig(suspicious_seconds=30.0, suspicious_approach_count=3,
                                           suspicious_approach_min_seconds=2.0,
                                           suspicious_gap_seconds=1.0, handover_max_gap_seconds=0.5))
    for track_id, start in enumerate((0.0, 10.0, 20.0, 30.0), start=1):
        obs = {"track_id": track_id, "zone_id": "zone_a", "inside": False,
               "warning": True, "position": (0.1 * track_id, 0.5)}
        engine.evaluate([obs], armed=True, now=start)
        result = engine.evaluate([obs], armed=True, now=start + 1.0)
        assert result.tracks[str(track_id)]["state"] != "SUSPICIOUS"
    assert all(track["state"] != "SUSPICIOUS" for track in result.tracks.values())


def test_two_simultaneous_buffer_tracks_do_not_combine_their_timers():
    engine = DecisionEngine(DecisionConfig(suspicious_seconds=30.0, suspicious_approach_count=99,
                                           handover_exclusion_radius=0.02))
    observations = [
        {"track_id": 1, "zone_id": "zone_a", "inside": False, "warning": True,
         "position": (0.25, 0.5)},
        {"track_id": 2, "zone_id": "zone_a", "inside": False, "warning": True,
         "position": (0.75, 0.5)},
    ]
    engine.evaluate(observations, armed=True, now=0.0)
    result = engine.evaluate(observations, armed=True, now=20.0)
    assert result.tracks["1"]["proximity_seconds"] == 20.0
    assert result.tracks["2"]["proximity_seconds"] == 20.0
    assert all(track["state"] != "SUSPICIOUS" for track in result.tracks.values())


def test_mid_frame_occlusion_can_still_allow_position_based_handover():
    engine = DecisionEngine(DecisionConfig(suspicious_seconds=30.0, suspicious_approach_count=99,
                                           handover_max_gap_seconds=3.5, handover_match_radius=0.08))
    old = {"track_id": 41, "zone_id": "zone_a", "inside": False, "warning": True,
           "position": (0.5, 0.5)}
    engine.evaluate([old], armed=True, now=0.0)
    engine.evaluate([old], armed=True, now=4.0)
    engine.evaluate([], armed=True, now=4.2)
    new = {"track_id": 42, "zone_id": "zone_a", "inside": False, "warning": True,
           "position": (0.505, 0.5)}
    result = engine.evaluate([new], armed=True, now=5.0)
    assert result.tracks["42"]["proximity_seconds"] >= 4.0


def test_edge_outward_flag_prevents_handover_but_missing_motion_does_not():
    engine = DecisionEngine(DecisionConfig(entry_grace_seconds=8.0, handover_max_gap_seconds=3.5))
    old = {"track_id": 921, "zone_id": "zone_a", "inside": True, "position": (0.02, 0.5),
           "exited_frame_edge": True}
    engine.evaluate([old], armed=True, now=0.0)
    engine.evaluate([old], armed=True, now=4.0)
    new = {"track_id": 922, "zone_id": "zone_a", "inside": True, "position": (0.02, 0.5)}
    result = engine.evaluate([new], armed=True, now=5.0)
    assert result.tracks["922"]["elapsed_seconds"] == 0.0


def test_decision_record_replay_matches_without_database_and_resets_sessions(tmp_path):
    from ai.decision import DecisionConfig, DecisionEngine
    from ai.decision_replay import append_frame_record, replay

    path = tmp_path / "capture.jsonl"
    config = DecisionConfig(entry_grace_seconds=8.0)
    for session_id, start in (("run-a", 0.0), ("run-b", 100.0)):
        engine = DecisionEngine(config)
        observations = [{"track_id": 1, "zone_id": "zone_a", "inside": True}]
        for index, now in enumerate((start, start + 5.0, start + 10.0), 1):
            result = engine.evaluate(observations, armed=True, now=now)
            append_frame_record(path, config=config, observations=observations, armed=True,
                now=now, anonymous_inside=False, health_fault=False, health_fault_elapsed=0.0,
                events=list(result.events), alarm_state=result.alarm_state,
                session_id=session_id, frame_seq=index, frame_size=(640, 480),
                session_start=index == 1)
    result = replay(path)
    assert result["frames"] == 6
    assert result["sessions"] == 2
    assert result["mismatches"] == 0


def test_decision_replay_overrides_compare_and_report_differences(tmp_path):
    from ai.decision import DecisionConfig, DecisionEngine
    from ai.decision_replay import append_frame_record, replay

    path = tmp_path / "capture.jsonl"
    config = DecisionConfig(entry_grace_seconds=8.0)
    engine = DecisionEngine(config)
    obs = [{"track_id": 2, "zone_id": "zone_a", "inside": True}]
    for index, now in enumerate((0.0, 6.0), 1):
        result = engine.evaluate(obs, armed=True, now=now)
        append_frame_record(path, config=config, observations=obs, armed=True, now=now,
            anonymous_inside=False, health_fault=False, health_fault_elapsed=0.0,
            events=list(result.events), alarm_state=result.alarm_state,
            session_id="override-run", frame_seq=index, session_start=index == 1)
    compared = replay(path, {"entry_grace_seconds": 5.0})
    assert compared["frames"] == 2
    assert compared["mismatches"] >= 1
    assert compared["differences"]
    assert compared["differences"][-1]["alarm_state"]["expected"] == "WARNING"
    assert compared["differences"][-1]["alarm_state"]["actual"] == "ALARM"



def test_replay_rotates_bounded_file_and_keeps_engine_state_across_rotation(tmp_path, monkeypatch):
    import json
    from ai.decision import DecisionConfig, DecisionEngine
    from ai.decision_replay import append_frame_record, replay

    path = tmp_path / "capture.jsonl"
    monkeypatch.setenv("KHOAI_DECISION_RECORD_MAX_BYTES", "4096")
    config = DecisionConfig(entry_grace_seconds=50.0)
    engine = DecisionEngine(config)
    obs = [{"track_id": 8, "zone_id": "zone_a", "inside": True}]
    for index in range(1, 10):
        now = float(index * 2)
        result = engine.evaluate(obs, armed=True, now=now)
        append_frame_record(path, config=config, observations=obs, armed=True, now=now,
            anonymous_inside=False, health_fault=False, health_fault_elapsed=0.0,
            events=list(result.events), alarm_state=result.alarm_state,
            session_id="rotating-run", frame_seq=index, session_start=index == 1)
    assert path.exists() and path.with_name(path.name + ".1").exists()
    assert path.stat().st_size <= 4096
    assert path.with_name(path.name + ".1").stat().st_size <= 4096
    report = replay(path)
    assert report["mismatches"] == 0
    assert report["frames"] >= 2


def test_handover_on_confirmed_raw_inside_frames_preserves_intrusion_session():
    """Raw geometry bridges detector hysteresis only after consecutive confirmation."""
    engine = DecisionEngine(DecisionConfig(entry_grace_seconds=8.0,
                                           handover_max_gap_seconds=3.5,
                                           handover_match_radius=0.1,
                                           handover_exclusion_radius=0.02,
                                           handover_raw_inside_confirm_seconds=0.22))
    first = engine.evaluate([{"track_id": 201, "zone_id": "zone_a", "inside": True,
                              "position": [0.5, 0.8]}], armed=True, now=0.0)
    session_id = first.tracks["201"]["session_id"]
    engine.evaluate([{"track_id": 201, "zone_id": "zone_a", "inside": True,
                      "position": [0.5, 0.8]}], armed=True, now=3.5)

    first_raw = engine.evaluate([{"track_id": 202, "zone_id": "zone_a", "inside": False,
                                  "raw_inside": True, "warning": False,
                                  "exit_boundary_inside": True,
                                  "position": [0.505, 0.8]}], armed=True, now=4.0)
    assert first_raw.tracks["202"]["session_id"] is None

    second_raw = engine.evaluate([{"track_id": 202, "zone_id": "zone_a", "inside": False,
                                   "raw_inside": True, "warning": False,
                                   "exit_boundary_inside": True,
                                   "position": [0.505, 0.8]}], armed=True, now=4.25)
    assert second_raw.tracks["202"]["session_id"] == session_id
    assert second_raw.tracks["202"]["elapsed_seconds"] >= 3.5
    assert second_raw.tracks["202"]["state"] == "WARNING"

    engine.evaluate([{"track_id": 202, "zone_id": "zone_a", "inside": True,
                      "raw_inside": True, "position": [0.505, 0.8]}],
                     armed=True, now=4.2)
    result = engine.evaluate([{"track_id": 202, "zone_id": "zone_a", "inside": True,
                               "raw_inside": True, "position": [0.505, 0.8]}],
                             armed=True, now=12.3)
    assert result.alarm_state == "ALARM"


def test_single_raw_inside_boundary_frame_cannot_inherit_intrusion_session():
    """One raw-inside frame followed by buffer-only presence must not claim the old session."""
    engine = DecisionEngine(DecisionConfig(entry_grace_seconds=8.0,
                                           handover_max_gap_seconds=3.5,
                                           handover_match_radius=0.1,
                                           handover_exclusion_radius=0.02,
                                           handover_raw_inside_confirm_seconds=0.22))
    first = engine.evaluate([{"track_id": 301, "zone_id": "zone_a", "inside": True,
                              "position": [0.5, 0.8]}], armed=True, now=0.0)
    old_session = first.tracks["301"]["session_id"]
    engine.evaluate([{"track_id": 301, "zone_id": "zone_a", "inside": True,
                      "position": [0.5, 0.8]}], armed=True, now=2.0)

    engine.evaluate([{"track_id": 302, "zone_id": "zone_a", "inside": False,
                      "raw_inside": True, "warning": False,
                      "position": [0.505, 0.8]}], armed=True, now=2.5)
    buffer_only = engine.evaluate([{"track_id": 302, "zone_id": "zone_a", "inside": False,
                                    "raw_inside": False, "warning": True,
                                    "position": [0.505, 0.8]}], armed=True, now=2.6)
    assert buffer_only.tracks["302"]["session_id"] is None
    assert buffer_only.tracks["302"]["session_id"] != old_session
    assert buffer_only.tracks["302"]["state"] in {"PASSERBY", "WARNING"}


def test_warning_only_handover_does_not_inherit_intrusion_session_even_with_raw_inside_false():
    engine = DecisionEngine(DecisionConfig(entry_grace_seconds=8.0,
                                           handover_match_radius=0.1))
    engine.evaluate([{"track_id": 211, "zone_id": "zone_a", "inside": True,
                      "position": [0.5, 0.8]}], armed=True, now=0.0)
    result = engine.evaluate([{"track_id": 212, "zone_id": "zone_a", "inside": False,
                               "raw_inside": False, "warning": True,
                               "position": [0.505, 0.8]}], armed=True, now=1.0)
    assert result.tracks["212"]["session_id"] is None
    assert result.tracks["212"]["elapsed_seconds"] == 0.0



@pytest.mark.parametrize("fps", [5, 10, 15, 25, 30])
def test_raw_inside_handover_confirmation_is_time_based_across_fps(fps):
    engine = DecisionEngine(DecisionConfig(entry_grace_seconds=8.0,
                                           handover_max_gap_seconds=3.5,
                                           handover_match_radius=0.1,
                                           handover_exclusion_radius=0.02,
                                           handover_raw_inside_confirm_seconds=0.22))
    first = engine.evaluate([{"track_id": 801, "zone_id": "zone_a", "inside": True,
                              "position": [0.5, 0.8]}], armed=True, now=0.0)
    old_session = first.tracks["801"]["session_id"]
    engine.evaluate([{"track_id": 801, "zone_id": "zone_a", "inside": True,
                      "position": [0.5, 0.8]}], armed=True, now=0.5)

    dt = 1.0 / fps
    start = 1.0
    before = None
    steps = int(0.15 / dt) + 1
    for i in range(steps):
        before = engine.evaluate([{"track_id": 802, "zone_id": "zone_a", "inside": False,
                                   "raw_inside": True, "warning": False,
                                   "position": [0.505, 0.8]}],
                                 armed=True, now=start + i * dt)
    assert before.tracks["802"]["session_id"] is None

    # Continue the same uninterrupted raw-inside observation until >= 0.22 s.
    i = steps
    result = None
    while i * dt < 0.22:
        engine.evaluate([{"track_id": 802, "zone_id": "zone_a", "inside": False,
                          "raw_inside": True, "warning": False,
                          "position": [0.505, 0.8]}],
                        armed=True, now=start + i * dt)
        i += 1
    result = engine.evaluate([{"track_id": 802, "zone_id": "zone_a", "inside": False,
                               "raw_inside": True, "warning": False,
                               "position": [0.505, 0.8]}],
                             armed=True, now=start + i * dt)
    assert result is not None
    assert result.tracks["802"]["session_id"] == old_session


def test_raw_inside_confirmation_resets_after_a_gap():
    engine = DecisionEngine(DecisionConfig(entry_grace_seconds=8.0,
                                           handover_max_gap_seconds=3.5,
                                           handover_match_radius=0.1,
                                           handover_exclusion_radius=0.02,
                                           handover_raw_inside_confirm_seconds=0.22))
    first = engine.evaluate([{"track_id": 811, "zone_id": "zone_a", "inside": True,
                              "position": [0.5, 0.8]}], armed=True, now=0.0)
    old_session = first.tracks["811"]["session_id"]
    engine.evaluate([{"track_id": 811, "zone_id": "zone_a", "inside": True,
                      "position": [0.5, 0.8]}], armed=True, now=0.5)
    engine.evaluate([{"track_id": 812, "zone_id": "zone_a", "inside": False,
                      "raw_inside": True, "position": [0.505, 0.8]}],
                    armed=True, now=1.0)
    engine.evaluate([{"track_id": 812, "zone_id": "zone_a", "inside": False,
                      "raw_inside": False, "warning": True,
                      "position": [0.505, 0.8]}],
                    armed=True, now=1.1)
    result = engine.evaluate([{"track_id": 812, "zone_id": "zone_a", "inside": False,
                               "raw_inside": True, "position": [0.505, 0.8]}],
                             armed=True, now=1.2)
    assert result.tracks["812"]["session_id"] is None
    assert result.tracks["812"]["session_id"] != old_session
