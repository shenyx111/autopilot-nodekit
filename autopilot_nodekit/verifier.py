from __future__ import annotations

import json
from typing import Any, Dict, Mapping


def parse_json_mapping(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if not value:
        return {}
    try:
        parsed = json.loads(str(value))
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def select_verifier(task: Mapping[str, Any] | Any, config: Dict[str, Any]) -> Dict[str, Any]:
    """Return the effective verifier configuration for a task.

    Precedence is task.verifier > config.verifier > no verifier.
    The returned mapping always includes `source` and `command` keys.
    """
    task_verifier = {}
    try:
        if "verifier_json" in task.keys():  # sqlite3.Row-like
            task_verifier = parse_json_mapping(task["verifier_json"])
    except Exception:
        task_verifier = {}
    if not task_verifier and isinstance(task, dict):
        task_verifier = parse_json_mapping(task.get("verifier") or task.get("verifier_json"))

    if task_verifier.get("enabled") is False:
        return {"source": "task-disabled", "command": "", "timeout_seconds": None, "require_for_pass": False}

    if str(task_verifier.get("command") or "").strip():
        out = dict(task_verifier)
        out["source"] = "task"
        return normalize_verifier(out)

    config_verifier = parse_json_mapping(config.get("verifier", {}) or {})
    if str(config_verifier.get("command") or "").strip():
        out = dict(config_verifier)
        out["source"] = "config"
        return normalize_verifier(out)

    return {"source": "none", "command": "", "timeout_seconds": None, "require_for_pass": False}


def normalize_verifier(verifier: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(verifier)
    out["command"] = str(out.get("command") or "")
    timeout = out.get("timeout_seconds")
    out["timeout_seconds"] = int(timeout) if timeout not in (None, "", 0, "0") else None
    out["require_for_pass"] = bool(out.get("require_for_pass", False))
    return out
