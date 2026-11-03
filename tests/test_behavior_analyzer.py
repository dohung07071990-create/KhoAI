from ai.behavior_analyzer import evaluate_behavior
POLICY = {"min_confidence": .7, "actions": {
    "walking": {"allowed_zones": ["*"], "requires_work_order": False},
    "pick_item": {"allowed_zones": ["storage"], "requires_work_order": True}}}
def test_allowed_action():
    assert evaluate_behavior("pick_item", .91,
        {"authorized": True, "zone": "storage", "work_order_valid": True}, POLICY).status == "ALLOWED"
def test_missing_context_review():
    assert evaluate_behavior("pick_item", .91,
        {"authorized": True, "zone": "storage"}, POLICY).status == "REVIEW"
def test_wrong_zone_abnormal():
    assert evaluate_behavior("pick_item", .91,
        {"authorized": True, "zone": "restricted", "work_order_valid": True}, POLICY).status == "ABNORMAL"
def test_unknown_action_review():
    assert evaluate_behavior("unknown_act", .99,
        {"authorized": True, "zone": "storage"}, POLICY).status == "REVIEW"
