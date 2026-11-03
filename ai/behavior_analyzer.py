"""Evaluate action-recognition labels against verified operational context.
This module does NOT infer actions from pixels; it evaluates model outputs.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Any, Mapping

@dataclass(frozen=True)
class BehaviorDecision:
    status: str
    action: str
    reason: str
    confidence: float
    evidence: dict[str, Any]
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

def evaluate_behavior(action: str, confidence: float, context: Mapping[str, Any],
                      policy: Mapping[str, Any]) -> BehaviorDecision:
    """Return ALLOWED, REVIEW, or ABNORMAL.

    Context: authorized (bool), zone (str), work_order_valid (bool).
    Policy: min_confidence and actions[label] with allowed_zones and
    requires_work_order.
    """
    label = str(action or "").strip().lower()
    try:
        score = max(0.0, min(1.0, float(confidence)))
    except (TypeError, ValueError):
        score = 0.0
    evidence = {k: context.get(k) for k in
                ("authorized", "zone", "work_order_valid")}
    threshold = float(policy.get("min_confidence", 0.70))
    rules = policy.get("actions", {})
    rule = rules.get(label) if isinstance(rules, Mapping) else None
    if not label or score < threshold:
        return BehaviorDecision("REVIEW", label or "unknown",
            "Nhãn hành động không rõ hoặc độ tin cậy thấp.", score, evidence)
    if not isinstance(rule, Mapping):
        return BehaviorDecision("REVIEW", label,
            "Hành động chưa có quy tắc được cấu hình.", score, evidence)
    if context.get("authorized") is not True:
        return BehaviorDecision("ABNORMAL", label,
            "Không xác minh được quyền của người thực hiện.", score, evidence)
    zone = context.get("zone")
    allowed_zones = rule.get("allowed_zones", [])
    if zone is None or not isinstance(allowed_zones, list):
        return BehaviorDecision("REVIEW", label,
            "Thiếu thông tin khu vực hoặc cấu hình khu vực.", score, evidence)
    if "*" not in allowed_zones and zone not in allowed_zones:
        return BehaviorDecision("ABNORMAL", label,
            "Hành động diễn ra ngoài khu vực được phép.", score, evidence)
    if rule.get("requires_work_order") and "work_order_valid" not in context:
        return BehaviorDecision("REVIEW", label,
            "Chưa có dữ liệu xác minh lệnh công việc.", score, evidence)
    if rule.get("requires_work_order") and context.get("work_order_valid") is not True:
        return BehaviorDecision("ABNORMAL", label,
            "Hành động yêu cầu lệnh công việc hợp lệ.", score, evidence)
    return BehaviorDecision("ALLOWED", label,
        "Hành động phù hợp với quy tắc và ngữ cảnh đã cung cấp.", score, evidence)
