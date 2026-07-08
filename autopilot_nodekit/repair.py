from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict

from .db import AutoDB
from .graph_patch import apply_graph_patch
from .util import slugify


def add_repair_task(db: AutoDB, failed_task_id: str, summary: str, *, priority: int | None = None) -> str:
    task = db.get_task(failed_task_id)
    if task is None:
        raise KeyError(f"Task not found: {failed_task_id}")
    existing = [t["id"] for t in db.list_tasks() if str(t["id"]).startswith(f"{failed_task_id}_REPAIR_")]
    n = len(existing) + 1
    repair_id = f"{failed_task_id}_REPAIR_{n:02d}"
    base_priority = int(task["priority"] or 0)
    repair_task: Dict[str, Any] = {
        "id": repair_id,
        "parent_id": failed_task_id,
        "title": f"Repair {failed_task_id}: {str(summary)[:80]}",
        "objective": (
            f"Repair the failure in {failed_task_id} using the smallest defensible patch. "
            "Read prior run evidence, identify the responsible files, apply a minimal change, and re-run the verifier."
        ),
        "success_criteria": (
            "The original failure reason is addressed, verifier evidence is recorded, and no unrelated broad rewrite is performed. "
            "If the repair cannot be completed, record blocker evidence and stop."
        ),
        "after_attempt": [failed_task_id],
        "priority": priority if priority is not None else base_priority + 1,
        "max_attempts": 2,
        "input_files": ["runs/", "automation/manifest.live.md", "GOAL_CONTRACT.yml"],
        "expected_outputs": [f"tasks/{failed_task_id}/repair_{n:02d}.md", "project_memory/failures.md"],
        "done_when": ["failure_reason is recorded", "responsible files are identified", "patch_summary exists", "verifier_output exists", "Santa dual-review returns NICE/NICE"],
        "review_policy": {
            "method": "santa_dual_review",
            "required": True,
            "reviewers": ["autopilot-santa-reviewer-a", "autopilot-santa-reviewer-b"],
        },
        "memory": {
            "required_task_ids": [failed_task_id],
            "required_tags": ["failure", "repair", "verifier"],
            "required_scopes": ["bug", "task", "tool", "decision"],
            "search_queries": [f"{failed_task_id} failure repair verifier {summary}"],
        },
    }
    apply_graph_patch(db, {"operations": [{"op": "add_task", "task": repair_task}]}, source="add-repair-task")
    db.event("repair_task_added", {"failed_task_id": failed_task_id, "repair_task_id": repair_id, "summary": summary}, task_id=repair_id, worker_id="human-or-control-plane")
    return repair_id
