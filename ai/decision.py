"""Pure, deterministic security decision engine for the USB-camera pipeline."""
from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any, Iterable, Mapping
import uuid


@dataclass(frozen=True)
class DecisionConfig:
    entry_grace_seconds: float = 8.0
    wrong_zone_grace_seconds: float = 8.0
    dwell_review_seconds: float = 300.0
    track_hold_seconds: float = 5.0
    handover_max_gap_seconds: float = 3.5
    handover_edge_margin_ratio: float = 0.03
    handover_match_radius: float = 0.08
    handover_exclusion_radius: float = 0.08
    handover_raw_inside_confirm_seconds: float = 0.22
    exit_hysteresis_seconds: float = 0.5
    presence_release_seconds: float = 8.0
    anonymous_debounce_seconds: float = 1.0
    health_escalation_seconds: float = 30.0
    passerby_confirm_seconds: float = 3.0
    suspicious_seconds: float = 30.0
    suspicious_gap_seconds: float = 4.0
    suspicious_approach_min_seconds: float = 2.0
    suspicious_approach_count: int = 3
    suspicious_approach_window_seconds: float = 120.0

    def __post_init__(self) -> None:
        values = (self.entry_grace_seconds, self.wrong_zone_grace_seconds,
                  self.dwell_review_seconds, self.track_hold_seconds,
                  self.handover_max_gap_seconds, self.handover_raw_inside_confirm_seconds,
                  self.handover_match_radius,
                  self.handover_exclusion_radius, self.exit_hysteresis_seconds,
                  self.presence_release_seconds, self.anonymous_debounce_seconds,
                  self.health_escalation_seconds, self.passerby_confirm_seconds,
                  self.suspicious_seconds, self.handover_edge_margin_ratio,
                  self.suspicious_gap_seconds, self.suspicious_approach_min_seconds,
                  self.suspicious_approach_window_seconds)
        if min(values) < 0:
            raise ValueError("Decision timeouts and ratios must be >= 0")
        if self.suspicious_approach_count < 1:
            raise ValueError("suspicious_approach_count must be >= 1")


@dataclass
class _Track:
    state: str = "OUTSIDE"
    entered_at: float | None = None
    last_seen: float = 0.0
    last_zone: str | None = None
    last_reason: str | None = None
    last_inside_at: float | None = None
    inside_elapsed: float = 0.0
    inside_last_tick: float | None = None
    inside_inactive_since: float | None = None
    last_position: tuple[float, float] | None = None
    exit_pending_since: float | None = None
    session_id: str | None = None
    last_exited_frame_edge: bool = False
    missing_since: float | None = None
    warning_elapsed: float = 0.0
    warning_last_tick: float | None = None
    warning_inactive_since: float | None = None
    warning_bout_counted: bool = False
    approach_times: list[float] = field(default_factory=list)


@dataclass(frozen=True)
class DecisionSnapshot:
    alarm_state: str
    armed: bool
    tracks: dict[str, dict[str, Any]]
    events: tuple[dict[str, Any], ...] = field(default_factory=tuple)


class DecisionEngine:
    """Single source of truth for per-track decisions and aggregate alarm."""

    def __init__(self, config: DecisionConfig | None = None) -> None:
        self.config = config or DecisionConfig()
        self._tracks: dict[str, _Track] = {}
        # Consecutive raw geometry hits for replacement IDs. A single boundary
        # frame must not transfer an existing intrusion session.
        self._handover_raw_inside_since: dict[str, float] = {}
        self._alarm_state = "SAFE"
        self._anonymous_since: float | None = None
        self._anonymous_missing_since: float | None = None
        self._anonymous_active = False

    @property
    def alarm_state(self) -> str:
        return self._alarm_state

    def reset(self) -> None:
        self._tracks.clear()
        self._handover_raw_inside_since.clear()
        self._anonymous_since = None
        self._anonymous_missing_since = None
        self._anonymous_active = False
        self._alarm_state = "SAFE"

    @staticmethod
    def _authorized_zones(obs: Mapping[str, Any]) -> set[str]:
        value = obs.get("authorized_zones")
        if not isinstance(value, (list, tuple, set, frozenset)):
            return set()
        return {zone.strip() for zone in value if isinstance(zone, str) and zone.strip()}

    @staticmethod
    def _dwell_seconds(obs: Mapping[str, Any]) -> float:
        value = obs.get("dwell_seconds", 0.0)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return 0.0
        try:
            seconds = float(value)
        except (OverflowError, TypeError, ValueError):
            return 0.0
        return seconds if math.isfinite(seconds) and seconds >= 0.0 else 0.0

    @staticmethod
    def _zone_key(obs: Mapping[str, Any]) -> str:
        zone = str(obs.get("zone_id") or "default")
        permitted = DecisionEngine._authorized_zones(obs)
        wrong_zone = bool(permitted and zone not in permitted)
        return f"{zone}:{'wrong' if wrong_zone else 'entry'}"

    def evaluate(self, observations: Iterable[Mapping[str, Any]], *, armed: bool,
                 now: float, anonymous_inside: bool = False, health_fault: bool = False,
                 health_fault_elapsed: float = 0.0) -> DecisionSnapshot:
        events: list[dict[str, Any]] = []
        current: dict[str, dict[str, Any]] = {}
        seen: set[str] = set()
        observations = list(observations)
        seen = {str(obs.get("track_id")) for obs in observations if obs.get("track_id") is not None}

        # Handover contract: `inside` is the Detector's hysteresis-confirmed entry
        # (normally after KHOAI_ENTER_CONFIRM_SECONDS, default 0.10 s) and is sufficient
        # for immediate session transfer. `raw_inside` is only the pre-hysteresis geometry
        # signal; it is NOT equivalent to confirmed entry. The Engine-side 0.22 s default
        # is a defensive fallback for delayed/custom/replayed observations where raw_inside
        # persists but `inside` has not arrived. In the normal detector pipeline, `inside`
        # should usually become true first, so this branch is intentionally exceptional.
        # The timer is continuous-time (not frame-count based) and resets on any missing
        # raw_inside observation, avoiding FPS-dependent boundary-touch handovers.
        next_raw_since: dict[str, float] = {}
        raw_inside_confirmed: set[str] = set()
        for obs in observations:
            raw_id = obs.get("track_id")
            if raw_id is None:
                continue
            tid = str(raw_id)
            if bool(obs.get("inside")):
                raw_inside_confirmed.add(tid)
                continue
            if bool(obs.get("raw_inside")):
                since = self._handover_raw_inside_since.get(tid, now)
                next_raw_since[tid] = since
                if max(0.0, now - since) >= self.config.handover_raw_inside_confirm_seconds:
                    raw_inside_confirmed.add(tid)
        self._handover_raw_inside_since = next_raw_since

        if not armed:
            self._anonymous_since = None
            self._anonymous_missing_since = None
            self._anonymous_active = False

        # Transfer an active timer only across an unambiguous short-lived tracker ID swap.
        # Positions are normalized footpoints; both sides must have exactly one candidate.
        new_positions: dict[str, tuple[float, float]] = {}
        for obs in observations:
            raw_id = obs.get("track_id")
            pos = obs.get("position")
            if raw_id is not None and isinstance(pos, (list, tuple)) and len(pos) == 2:
                try:
                    new_positions[str(raw_id)] = (float(pos[0]), float(pos[1]))
                except (TypeError, ValueError):
                    pass
        candidates: dict[str, list[str]] = {}
        reverse: dict[str, list[str]] = {}
        observation_by_id = {str(item.get("track_id")): item for item in observations
                             if item.get("track_id") is not None}
        for new_id, pos in new_positions.items():
            existing_new = self._tracks.get(new_id)
            if existing_new is not None and (
                existing_new.session_id is not None
                or existing_new.state in {"WARNING", "SUSPICIOUS", "ALARM", "AUTHORIZED"}
            ):
                continue
            new_obs = observation_by_id.get(new_id, {})
            raw_unconfirmed = bool(new_obs.get("raw_inside")) and new_id not in raw_inside_confirmed \
                and not bool(new_obs.get("inside"))
            # Do not consume the old session as proximity-only while raw geometry
            # is still being confirmed. If confirmation fails, a later buffer-only
            # observation may still inherit proximity memory without the session.
            if raw_unconfirmed:
                continue
            # Confirmed inside and warning-buffer observations can be considered
            # immediately. Raw geometry alone needs consecutive-frame confirmation.
            if not (bool(new_obs.get("inside")) or new_id in raw_inside_confirmed
                    or bool(new_obs.get("warning"))):
                continue
            new_zone = str(new_obs.get("zone_id") or "")
            new_permitted = self._authorized_zones(new_obs)
            if new_zone and new_zone in new_permitted:
                continue
            for old_id, old in self._tracks.items():
                if old_id in seen or old.last_position is None:
                    continue
                # Handover is deliberately shorter than the normal Track retention
                # window: long disappearances are not reliable identity continuity.
                if now - old.last_seen > self.config.handover_max_gap_seconds:
                    continue
                # A Track last observed at the image boundary is presumed to have
                # exited the camera view; do not transfer its timer to a newcomer.
                if old.last_exited_frame_edge:
                    continue
                if old.state not in {"PASSERBY", "WARNING", "SUSPICIOUS", "ALARM"}:
                    continue
                old_zone = old.last_zone or ""
                if str(new_obs.get("zone_id") or "") != old_zone:
                    continue
                # If a different, already-known Track is still visible at the old
                # position, that Track explains the old location. Do not let a new
                # ID claim the missing Track's timer merely by appearing nearby.
                explained_by_live_track = False
                for live_id in seen:
                    if live_id == old_id or live_id == new_id:
                        continue
                    live = self._tracks.get(live_id)
                    live_position = new_positions.get(live_id) or (live.last_position if live else None)
                    if live_position is None or (live is not None and live.state == "AUTHORIZED"):
                        continue
                    live_distance = ((live_position[0] - old.last_position[0]) ** 2 +
                                     (live_position[1] - old.last_position[1]) ** 2) ** 0.5
                    if live_distance <= self.config.handover_exclusion_radius:
                        explained_by_live_track = True
                        break
                if explained_by_live_track:
                    continue
                distance = ((pos[0] - old.last_position[0]) ** 2 +
                            (pos[1] - old.last_position[1]) ** 2) ** 0.5
                if distance <= self.config.handover_match_radius:
                    candidates.setdefault(new_id, []).append(old_id)
                    reverse.setdefault(old_id, []).append(new_id)
        for new_id, old_ids in candidates.items():
            if len(old_ids) != 1:
                continue
            old_id = old_ids[0]
            if len(reverse.get(old_id, [])) != 1:
                continue
            # ID continuity in the warning buffer transfers proximity memory only.
            # An intrusion session, inside timer, ALARM state, or authorization must
            # never be inherited by a new ID that is merely outside the protected zone.
            old_track = self._tracks.pop(old_id)
            new_obs = observation_by_id.get(new_id, {})
            if bool(new_obs.get("inside")) or new_id in raw_inside_confirmed:
                # Raw geometry bridges detector entry hysteresis only after the
                # configured consecutive-frame confirmation threshold is reached.
                self._tracks[new_id] = old_track
            else:
                # A warning-buffer occupant inherits proximity memory only. It must
                # not inherit entered_at/session_id/inside_elapsed/ALARM state.
                new_track = _Track()
                new_track.warning_elapsed = old_track.warning_elapsed
                new_track.warning_last_tick = old_track.warning_last_tick
                new_track.warning_inactive_since = old_track.warning_inactive_since
                new_track.warning_bout_counted = old_track.warning_bout_counted
                new_track.approach_times = list(old_track.approach_times)
                new_track.last_zone = old_track.last_zone
                self._tracks[new_id] = new_track

        # Intrusion/session timers remain tied to a specific active Track ID.
        for obs in observations:
            raw_id = obs.get("track_id")
            if raw_id is None:
                continue
            tid = str(raw_id)
            seen.add(tid)
            track = self._tracks.setdefault(tid, _Track())
            previous = track.state
            track.last_seen = now
            track.missing_since = None
            pos = obs.get("position")
            track.last_exited_frame_edge = bool(obs.get("exited_frame_edge", False))
            if isinstance(pos, (list, tuple)) and len(pos) == 2:
                try:
                    track.last_position = (float(pos[0]), float(pos[1]))
                except (TypeError, ValueError):
                    pass
            zone_id = str(obs.get("zone_id") or "")
            inside = bool(obs.get("inside"))
            exit_confirmed = False
            # An active unauthorized session enters a release window after the
            # spatial/temporal exit confirmation. Re-entry before release resumes
            # the same session instead of creating a new incident/session ID.
            active_intrusion_session = (
                armed and track.session_id is not None and track.entered_at is not None
                and track.state in {"WARNING", "ALARM"}
            )
            if active_intrusion_session and not inside and track.inside_inactive_since is None:
                if bool(obs.get("exit_boundary_inside", False)):
                    track.exit_pending_since = None
                    inside = True
                else:
                    if track.exit_pending_since is None:
                        track.exit_pending_since = now
                    if now - track.exit_pending_since < self.config.exit_hysteresis_seconds:
                        inside = True
                    else:
                        track.exit_pending_since = None
                        exit_confirmed = True
            elif inside:
                track.exit_pending_since = None
            warning = bool(obs.get("warning"))
            permitted = self._authorized_zones(obs)
            authorized = bool(zone_id and zone_id in permitted)
            behavior_review = bool(obs.get("behavior_review"))
            dwell_seconds = self._dwell_seconds(obs)

            grace_remaining = None
            if not armed:
                next_state, reason = ("REVIEW", "behavior") if behavior_review else ("SAFE", None)
                track.session_id = None
                track.inside_elapsed = 0.0
                track.inside_last_tick = None
                track.inside_inactive_since = None
                track.entered_at = now if inside else None
                track.last_inside_at = now if inside else None
                track.exit_pending_since = None
                track.warning_elapsed = 0.0
                track.warning_last_tick = None
                track.warning_inactive_since = None
                track.warning_bout_counted = False
                track.approach_times.clear()
            elif not inside:
                # First confirmed exit pauses the occupancy clock but keeps the
                # session and its state alive for PRESENCE_RELEASE_SECONDS.
                if active_intrusion_session and exit_confirmed:
                    if track.inside_last_tick is not None:
                        track.inside_elapsed += max(0.0, now - track.inside_last_tick)
                    track.inside_last_tick = None
                    track.inside_inactive_since = now

                if active_intrusion_session and track.inside_inactive_since is not None:
                    inactive_for = max(0.0, now - track.inside_inactive_since)
                    grace_at_exit = (self.config.wrong_zone_grace_seconds
                                     if (track.last_reason or "").startswith("wrong_zone")
                                     else self.config.entry_grace_seconds)
                    # Grace includes the exit-confirmation interval (safety-first),
                    # but pauses after exit is confirmed while presence is released.
                    if track.inside_elapsed >= grace_at_exit and track.state != "ALARM":
                        next_state = "ALARM"
                        reason = "wrong_zone" if (track.last_reason or "").startswith("wrong_zone") else "unauthorized_entry"
                        events.append({"type": reason, "track_id": raw_id,
                                       "session_id": track.session_id, "zone": track.last_zone,
                                       "severity": "critical", "state": "ALARM"})
                    elif inactive_for < self.config.presence_release_seconds:
                        next_state, reason = track.state, track.last_reason
                    else:
                        # The session is closed exactly once, only after the
                        # release window. A short attempt is emitted at closure.
                        if track.state == "WARNING" and track.inside_elapsed >= 5.0:
                            events.append({"type": "intrusion_attempt_aborted", "track_id": raw_id,
                                           "session_id": track.session_id, "zone": track.last_zone,
                                           "severity": "warning", "duration_seconds": round(track.inside_elapsed, 2),
                                           "reason": "unauthorized_exit_before_alarm"})
                        next_state, reason = "SAFE", None
                        track.session_id = None
                        track.entered_at = None
                        track.last_inside_at = None
                        track.inside_elapsed = 0.0
                        track.inside_inactive_since = None
                        track.inside_last_tick = None
                else:
                    next_state, reason = None, None
                    if track.inside_inactive_since is None:
                        track.inside_inactive_since = now
                    track.inside_last_tick = None

                # Warning-zone proximity is tracked independently from intrusion
                # sessions. Short exits pause (do not add) the timer; a longer gap
                # resets continuous duration, while qualified approaches are counted
                # in a rolling window.
                if next_state is None and warning and not authorized:
                    if track.warning_last_tick is None:
                        if (track.warning_inactive_since is not None and
                                now - track.warning_inactive_since > self.config.suspicious_gap_seconds):
                            track.warning_elapsed = 0.0
                            track.warning_bout_counted = False
                        track.warning_inactive_since = None
                        track.warning_last_tick = now
                    else:
                        track.warning_elapsed += max(0.0, now - track.warning_last_tick)
                        track.warning_last_tick = now

                    track.approach_times = [stamp for stamp in track.approach_times
                        if now - stamp <= self.config.suspicious_approach_window_seconds]
                    if (not track.warning_bout_counted and
                            track.warning_elapsed >= self.config.suspicious_approach_min_seconds):
                        track.approach_times.append(now)
                        track.warning_bout_counted = True

                    if (track.warning_elapsed >= self.config.suspicious_seconds or
                            len(track.approach_times) >= self.config.suspicious_approach_count):
                        next_state, reason = "SUSPICIOUS", "repeated_or_prolonged_zone_proximity"
                    elif track.warning_elapsed >= self.config.passerby_confirm_seconds:
                        next_state, reason = "WARNING", "zone_proximity"
                    else:
                        next_state, reason = "PASSERBY", "brief_zone_proximity"
                elif next_state is None:
                    if track.warning_last_tick is not None:
                        track.warning_last_tick = None
                        track.warning_inactive_since = now
                    gap = (now - track.warning_inactive_since
                           if track.warning_inactive_since is not None else float("inf"))
                    if previous == "SUSPICIOUS" and gap <= self.config.suspicious_gap_seconds:
                        next_state, reason = "SUSPICIOUS", "repeated_or_prolonged_zone_proximity"
                    else:
                        if gap > self.config.suspicious_gap_seconds:
                            track.warning_elapsed = 0.0
                            track.warning_bout_counted = False
                        next_state, reason = "SAFE", None
            elif authorized:
                track.session_id = None
                track.warning_elapsed = 0.0
                track.warning_last_tick = None
                track.warning_inactive_since = None
                track.warning_bout_counted = False
                track.approach_times.clear()
                track.inside_elapsed = 0.0
                track.inside_last_tick = None
                track.inside_inactive_since = now
                track.exit_pending_since = None
                if track.entered_at is None:
                    track.entered_at = now
                if behavior_review or dwell_seconds >= self.config.dwell_review_seconds:
                    next_state, reason = "REVIEW", "authorized_behavior_or_dwell"
                else:
                    next_state, reason = "AUTHORIZED", None
            else:
                if track.entered_at is None:
                    track.entered_at = now
                if track.inside_inactive_since is not None:
                    inactive_for = max(0.0, now - track.inside_inactive_since)
                    if inactive_for >= self.config.presence_release_seconds:
                        # The previous session expired before this re-entry.
                        if track.state == "WARNING" and track.inside_elapsed >= 5.0 and track.session_id:
                            events.append({"type": "intrusion_attempt_aborted", "track_id": raw_id,
                                           "session_id": track.session_id, "zone": track.last_zone,
                                           "severity": "warning", "duration_seconds": round(track.inside_elapsed, 2),
                                           "reason": "unauthorized_exit_before_alarm"})
                        track.session_id = None
                        track.entered_at = None
                        track.inside_elapsed = 0.0
                        track.last_inside_at = None
                        track.state = "SAFE"
                        previous = "SAFE"
                    track.inside_inactive_since = None
                    track.inside_last_tick = None
                if track.session_id is None:
                    track.session_id = uuid.uuid4().hex
                if track.entered_at is None:
                    track.entered_at = now
                if track.inside_last_tick is not None:
                    track.inside_elapsed += max(0.0, now - track.inside_last_tick)
                track.inside_last_tick = now
                track.last_inside_at = now
                key = self._zone_key(obs)
                grace = (self.config.wrong_zone_grace_seconds
                         if key.endswith(":wrong") else self.config.entry_grace_seconds)
                # entered_at belongs to this track, so sequential passersby cannot
                # accumulate one another's time toward an alarm.
                elapsed = track.inside_elapsed
                if bool(obs.get("immediate_alarm")):
                    elapsed = max(elapsed, grace)
                grace_remaining = max(0.0, grace - elapsed)
                if elapsed >= grace:
                    next_state, reason = "ALARM", "wrong_zone" if key.endswith(":wrong") else "unauthorized_entry"
                else:
                    next_state, reason = "WARNING", "wrong_zone_pending" if key.endswith(":wrong") else "authorization_pending"

            track.state = next_state
            track.last_zone = zone_id or track.last_zone
            track.last_reason = reason
            if next_state == "ALARM" and previous != "ALARM":
                events.append({"type": reason or "unauthorized_entry", "track_id": raw_id,
                               "session_id": track.session_id, "zone": zone_id, "severity": "critical", "state": "ALARM"})
            elif next_state == "SUSPICIOUS" and previous != "SUSPICIOUS":
                events.append({"type": "suspicious_presence", "track_id": raw_id,
                               "zone": zone_id, "severity": "warning", "state": "SUSPICIOUS",
                               "reason": reason, "duration_seconds": round(track.warning_elapsed, 2),
                               "approach_count": len(track.approach_times)})
            elif next_state == "REVIEW" and previous != "REVIEW" and reason:
                events.append({"type": "review_required", "track_id": raw_id,
                               "zone": zone_id, "severity": "medium", "state": "REVIEW",
                               "reason": reason})
            elif next_state == "WARNING" and previous not in {"WARNING", "ALARM"}:
                events.append({"type": "access_pending" if reason != "zone_proximity" else "zone_warning",
                               "track_id": raw_id, "zone": zone_id, "severity": "warning",
                               "state": "WARNING", "reason": reason})
            current[tid] = {"track_id": raw_id, "state": next_state, "zone": zone_id or None,
                            "authorized": authorized, "reason": reason, "session_id": track.session_id,
                            "elapsed_seconds": round(max(0.0, now - track.entered_at), 2)
                            if track.entered_at is not None else 0.0,
                            "grace_remaining": round(grace_remaining, 2)
                            if grace_remaining is not None else None,
                            "proximity_seconds": round(track.warning_elapsed, 2),
                            "approach_count": len(track.approach_times)}

        # Keep state across short occlusions; each track's grace timer pauses during gaps.
        for tid in list(self._tracks):
            if tid not in seen:
                track = self._tracks[tid]
                if track.missing_since is None:
                    track.missing_since = now
                if track.inside_inactive_since is None:
                    track.inside_inactive_since = now
                track.inside_last_tick = None
                if track.warning_last_tick is not None:
                    track.warning_last_tick = None
                    track.warning_inactive_since = now
            if tid not in seen and now - self._tracks[tid].last_seen > self.config.track_hold_seconds:
                expired_track = self._tracks[tid]
                # A Track that disappears before the presence-release timer expires
                # must still close its WARNING attempt; otherwise hit-and-run attempts
                # vanish without an auditable event.
                if (armed and expired_track.state == "WARNING"
                        and expired_track.session_id
                        and expired_track.inside_elapsed >= 5.0):
                    try:
                        event_track_id = int(tid)
                    except (TypeError, ValueError):
                        event_track_id = -1
                    events.append({"type": "intrusion_attempt_aborted",
                                   "track_id": event_track_id, "session_id": expired_track.session_id,
                                   "zone": expired_track.last_zone, "severity": "warning",
                                   "duration_seconds": round(expired_track.inside_elapsed, 2),
                                   "reason": "track_lost_before_presence_release",
                                   "lost_at": expired_track.last_seen,
                                   "emitted_at": now})
                del self._tracks[tid]

        retained_states = {track.state for tid, track in self._tracks.items()
                           if tid not in seen and now - track.last_seen <= self.config.track_hold_seconds}
        states = {item["state"] for item in current.values()} | retained_states
        if not armed:
            aggregate = "SAFE"
        else:
            track_level = "ALARM" if "ALARM" in states else (
                "WARNING" if states.intersection({"WARNING", "SUSPICIOUS"}) else "SAFE"
            )
            if anonymous_inside:
                self._anonymous_missing_since = None
                if self._anonymous_since is None:
                    self._anonymous_since = now
                if now - self._anonymous_since >= self.config.anonymous_debounce_seconds:
                    if not self._anonymous_active:
                        events.append({"type": "anonymous_zone_alarm", "track_id": -1,
                                       "zone": None, "severity": "critical", "state": "ALARM"})
                    self._anonymous_active = True
            else:
                self._anonymous_since = None
                if self._anonymous_active:
                    if self._anonymous_missing_since is None:
                        self._anonymous_missing_since = now
                    if now - self._anonymous_missing_since >= self.config.track_hold_seconds:
                        self._anonymous_active = False
                        self._anonymous_missing_since = None
            # Anonymous and health faults can raise, never lower, the known-track aggregate.
            aggregate = "ALARM" if self._anonymous_active else track_level
            if health_fault:
                health_level = ("ALARM" if self.config.health_escalation_seconds == 0
                                or health_fault_elapsed >= self.config.health_escalation_seconds
                                else "WARNING")
                if health_level == "ALARM" or (health_level == "WARNING" and aggregate == "SAFE"):
                    aggregate = health_level

        if aggregate != self._alarm_state:
            events.append({"type": "alarm_state_changed", "track_id": -1,
                           "severity": "critical" if aggregate == "ALARM" else
                                      "warning" if aggregate == "WARNING" else "info",
                           "state": aggregate, "previous_state": self._alarm_state})
        self._alarm_state = aggregate
        return DecisionSnapshot(aggregate, bool(armed), current, tuple(events))
