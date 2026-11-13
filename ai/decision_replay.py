"""Opt-in, bounded JSONL capture/replay for deterministic DecisionEngine regression."""
from __future__ import annotations

import argparse
import json
import logging
import os
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .decision import DecisionConfig, DecisionEngine

ALGORITHM_VERSION = "khoai-decision-v2"
DEFAULT_MAX_BYTES = 20 * 1024 * 1024
DEFAULT_MAX_AGE_DAYS = 7
logger = logging.getLogger(__name__)


def _retention_days() -> float:
    try:
        return max(0.0, float(os.getenv("KHOAI_DECISION_RECORD_MAX_AGE_DAYS", str(DEFAULT_MAX_AGE_DAYS))))
    except ValueError:
        return float(DEFAULT_MAX_AGE_DAYS)


def _prune_old_files(target: Path, backup: Path, max_age_days: float) -> None:
    if max_age_days <= 0:
        return
    cutoff = datetime.now(timezone.utc).timestamp() - max_age_days * 86400.0
    for candidate in (target, backup):
        try:
            if candidate.exists() and candidate.stat().st_mtime < cutoff:
                candidate.unlink()
        except OSError:
            logger.warning("Không thể dọn bản ghi Decision Engine cũ: %s", candidate, exc_info=True)


def append_frame_record(path: str | Path, *, config: DecisionConfig,
                        observations: list[Mapping[str, Any]], armed: bool, now: float,
                        anonymous_inside: bool, health_fault: bool,
                        health_fault_elapsed: float, events: list[Mapping[str, Any]],
                        alarm_state: str, session_id: str = "legacy",
                        frame_seq: int | None = None,
                        frame_size: tuple[int, int] | None = None,
                        session_start: bool = False) -> bool:
    """Append engine inputs/outputs. One active file + one bounded rotated file."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    backup = target.with_name(target.name + ".1")
    max_bytes = max(1024, int(os.getenv("KHOAI_DECISION_RECORD_MAX_BYTES", str(DEFAULT_MAX_BYTES))))
    _prune_old_files(target, backup, _retention_days())

    header = {
        "kind": "session_start", "algorithm_version": ALGORITHM_VERSION,
        "session_id": str(session_id), "recorded_at": datetime.now(timezone.utc).isoformat(),
        "config": asdict(config),
    }
    record = {
        "kind": "decision_frame", "algorithm_version": ALGORITHM_VERSION,
        "session_id": str(session_id), "frame_seq": frame_seq,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "frame_size": list(frame_size) if frame_size else None,
        "input": {
            "observations": [dict(item) for item in observations], "armed": bool(armed),
            "now": float(now), "anonymous_inside": bool(anonymous_inside),
            "health_fault": bool(health_fault),
            "health_fault_elapsed": float(health_fault_elapsed)},
        "expected": {"events": [dict(event) for event in events], "alarm_state": alarm_state}}
    lines = []
    if session_start or not target.exists():
        lines.append(json.dumps(header, ensure_ascii=False, separators=(",", ":")))
    lines.append(json.dumps(record, ensure_ascii=False, separators=(",", ":")))
    payload = "\n".join(lines) + "\n"
    payload_bytes = len(payload.encode("utf-8"))
    current_size = target.stat().st_size if target.exists() else 0
    if payload_bytes > max_bytes:
        logger.warning("Bỏ qua frame replay vì riêng bản ghi đã vượt giới hạn %s byte", max_bytes)
        return False
    if current_size + payload_bytes > max_bytes:
        try:
            if backup.exists():
                backup.unlink()
            if target.exists():
                target.replace(backup)
            # A rotated file is a separate replay segment; repeat the header in the new file.
            if not session_start:
                payload = (json.dumps(header, ensure_ascii=False, separators=(",", ":")) + "\n" +
                           json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
            logger.warning("Decision replay đạt giới hạn %s byte; đã xoay file sang %s", max_bytes, backup)
        except OSError:
            logger.exception("Không thể xoay file Decision replay; bỏ qua frame")
            return False
    try:
        with target.open("a", encoding="utf-8") as stream:
            stream.write(payload)
    except OSError:
        logger.exception("Không ghi được Decision replay vào %s", target)
        return False
    return True


def _stable_events(items: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [{key: value for key, value in item.items() if key not in {"session_id", "event_id"}}
            for item in items]


def replay(path: str | Path, overrides: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Replay every session independently; no camera, backend, or database imports."""
    target = Path(path)
    files = [target.with_name(target.name + ".1"), target]
    engine: DecisionEngine | None = None
    active_session: str | None = None
    config_values: dict[str, Any] | None = None
    frames = mismatches = sessions = 0
    differences: list[dict[str, Any]] = []
    for source in files:
        if not source.exists():
            continue
        for line_number, line in enumerate(source.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            record = json.loads(line)
            kind = record.get("kind")
            if kind == "session_start":
                if record.get("algorithm_version") != ALGORITHM_VERSION:
                    raise ValueError(f"Unsupported algorithm version in {source}:{line_number}")
                incoming_session = str(record.get("session_id") or f"{source}:{line_number}")
                if incoming_session != active_session:
                    active_session = incoming_session
                    config_values = dict(record["config"])
                    config_values.update(overrides or {})
                    engine = DecisionEngine(DecisionConfig(**config_values))
                    sessions += 1
                continue
            if kind != "decision_frame":
                continue
            if record.get("algorithm_version") != ALGORITHM_VERSION:
                raise ValueError(f"Unsupported algorithm version in {source}:{line_number}")
            session = str(record.get("session_id") or "legacy")
            if engine is None or session != active_session:
                # Backward-compatible support for the earlier per-frame config format.
                if "config" not in record:
                    raise ValueError(f"Missing session config before frame in {source}:{line_number}")
                active_session = session
                config_values = dict(record["config"])
                config_values.update(overrides or {})
                engine = DecisionEngine(DecisionConfig(**config_values))
                sessions += 1
            data = record["input"]
            result = engine.evaluate(data["observations"], armed=data["armed"], now=data["now"],
                anonymous_inside=data.get("anonymous_inside", False),
                health_fault=data.get("health_fault", False),
                health_fault_elapsed=data.get("health_fault_elapsed", 0.0))
            frames += 1
            expected = record.get("expected", {})
            actual_events = _stable_events(list(result.events))
            expected_events = _stable_events(expected.get("events", []))
            alarm_diff = result.alarm_state != expected.get("alarm_state")
            event_diff = actual_events != expected_events
            if alarm_diff or event_diff:
                mismatches += 1
                if len(differences) < 100:
                    differences.append({
                        "session_id": active_session, "frame_seq": record.get("frame_seq"),
                        "source": source.name, "line": line_number,
                        "alarm_state": {"expected": expected.get("alarm_state"), "actual": result.alarm_state}
                            if alarm_diff else None,
                        "events": {"expected": expected_events, "actual": actual_events}
                            if event_diff else None,
                    })
    return {"frames": frames, "sessions": sessions, "mismatches": mismatches,
            "overrides": dict(overrides or {}), "differences": differences}


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay KhoAI Decision Engine JSONL without camera or DB")
    parser.add_argument("record", help="Path to JSONL capture")
    parser.add_argument("--set", action="append", default=[], metavar="KEY=VALUE",
                        help="Override DecisionConfig field; repeat as needed")
    args = parser.parse_args()
    overrides: dict[str, Any] = {}
    for item in args.set:
        key, sep, raw = item.partition("=")
        if not sep:
            parser.error(f"Invalid override: {item}")
        try:
            overrides[key] = json.loads(raw)
        except json.JSONDecodeError:
            overrides[key] = raw
    print(json.dumps(replay(args.record, overrides), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
