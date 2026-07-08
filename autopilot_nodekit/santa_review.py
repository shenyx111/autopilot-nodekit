from __future__ import annotations

import json
from typing import Any, Dict, List, Tuple


NICE = "nice"


def parse_json_field(value: Any, default: Any = None) -> Any:
    if default is None:
        default = {}
    if value is None or value == "":
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(str(value))
    except Exception:
        return default


def review_required_for_task(task: Any, config: Dict[str, Any] | None = None) -> bool:
    """Return whether a passed result needs Santa dual review evidence.

    Human gate tasks are approved by humans and are not claimed by workers, so the
    enforcement applies to worker-executed tasks. Figure plans set the policy in
    task_contract_json; config can also opt in globally.
    """
    config = config or {}
    task_contract = parse_json_field(task["task_contract_json"] if hasattr(task, "keys") and "task_contract_json" in task.keys() else None, {})
    if bool(task_contract.get("human_review_required")):
        return False
    policy = task_contract.get("review_policy") if isinstance(task_contract.get("review_policy"), dict) else {}
    if policy.get("required") is not None:
        return bool(policy.get("required"))
    review_cfg = config.get("review", {}) or {}
    return bool(review_cfg.get("require_santa_for_pass", False))


def evaluate_santa_review(result: Dict[str, Any], task: Any, config: Dict[str, Any] | None = None) -> Tuple[bool, List[str], Dict[str, Any]]:
    required = review_required_for_task(task, config)
    review = result.get("review") if isinstance(result.get("review"), dict) else {}
    policy_name = str(review.get("policy") or review.get("method") or "").strip().lower()
    errors: List[str] = []
    if not required:
        return True, [], {"required": False, "policy": policy_name or "none"}
    if policy_name not in {"santa_dual_review", "santa-method", "santa_method", "dual_review"}:
        errors.append("review.policy must be santa_dual_review")
    task_contract = parse_json_field(task["task_contract_json"] if hasattr(task, "keys") and "task_contract_json" in task.keys() else None, {})
    task_policy = task_contract.get("review_policy") if isinstance(task_contract.get("review_policy"), dict) else {}
    expected_reviewers = task_policy.get("reviewers") if isinstance(task_policy.get("reviewers"), list) else []
    reviewer_keys = ["reviewer_a", "reviewer_b"]
    for idx, key in enumerate(reviewer_keys):
        item = review.get(key)
        if not isinstance(item, dict):
            errors.append(f"review.{key} missing")
            continue
        status = str(item.get("status") or item.get("verdict") or "").strip().lower()
        if status != NICE:
            errors.append(f"review.{key}.status must be NICE")
        summary = str(item.get("summary") or "").strip()
        evidence = item.get("evidence")
        if not summary:
            errors.append(f"review.{key}.summary missing")
        if not (isinstance(evidence, list) and len(evidence) > 0) and not str(evidence or "").strip():
            errors.append(f"review.{key}.evidence missing")
        if len(expected_reviewers) > idx:
            expected = str(expected_reviewers[idx]).strip()
            actual = str(item.get("agent") or item.get("reviewer") or item.get("subagent") or "").strip()
            if actual != expected:
                errors.append(f"review.{key}.agent must be {expected}")
    meta = {
        "required": True,
        "policy": policy_name or "missing",
        "reviewer_a_status": str((review.get("reviewer_a") or {}).get("status") or ""),
        "reviewer_b_status": str((review.get("reviewer_b") or {}).get("status") or ""),
        "errors": errors,
    }
    return not errors, errors, meta
