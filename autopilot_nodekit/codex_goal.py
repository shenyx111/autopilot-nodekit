from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from .db import AutoDB
from .util import load_yaml, read_text, write_text, workspace_paths
from .verifier import select_verifier


def _as_dict(row: Mapping[str, Any] | Any) -> dict[str, Any]:
    try:
        return {k: row[k] for k in row.keys()}
    except Exception:
        return dict(row)


def _clip(value: Any, limit: int = 420) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def _parse_json(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if not value:
        return {}
    try:
        parsed = json.loads(str(value))
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _load_project_goal(workspace: Path) -> str:
    paths = workspace_paths(workspace)
    try:
        data = load_yaml(paths["manifest"])
    except Exception:
        return ""
    project = data.get("project") or {}
    if isinstance(project, dict):
        return str(project.get("goal") or "")
    return ""


def _load_config(workspace: Path) -> dict[str, Any]:
    paths = workspace_paths(workspace)
    try:
        return load_yaml(paths["config"])
    except Exception:
        return {}


def select_task_for_goal(db: AutoDB, task_id: str | None = None) -> dict[str, Any]:
    db.refresh_ready_tasks()
    if task_id:
        row = db.get_task(task_id)
        if row is None:
            raise KeyError(f"Task not found: {task_id}")
        return _as_dict(row)
    ready = [t for t in db.list_tasks() if t["status"] == "ready"]
    if ready:
        return _as_dict(ready[0])
    nonterminal = [t for t in db.list_tasks() if t["status"] in {"planned", "blocked", "failed", "running"}]
    if nonterminal:
        return _as_dict(nonterminal[0])
    rows = db.list_tasks()
    if not rows:
        raise KeyError("No tasks found. Import a manifest first.")
    return _as_dict(rows[0])


def build_codex_goal(workspace: Path, db: AutoDB, task_id: str | None = None, worker_id: str = "codex-goal") -> dict[str, Any]:
    """Build a native Codex `/goal` command for an Autopilot NodeKit task.

    The result is deliberately short enough for Codex's 4,000-character goal limit.
    Longer operational details stay in AGENTS.md, PLANS.md, LOOP_STATE.md, and the
    NodeKit context pack.
    """
    workspace = workspace.resolve()
    task = select_task_for_goal(db, task_id)
    config = _load_config(workspace)
    verifier = select_verifier(task, config)
    project_goal = _load_project_goal(workspace)
    memory_policy = _parse_json(task.get("memory_policy_json"))

    verifier_command = str(verifier.get("command") or "").strip()
    if verifier_command:
        verifier_text = f"`{_clip(verifier_command, 520)}`"
    else:
        verifier_text = "the task-specific verifier if one is discovered; otherwise `python -m autopilot_nodekit validate --workspace .` plus explicit evidence in worker_result.json"

    required_tasks = memory_policy.get("required_task_ids") or []
    required_bits = ""
    if required_tasks:
        required_bits = " Required memory/task context: " + ", ".join(str(x) for x in required_tasks[:12]) + "."

    status = task.get("status") or "unknown"
    body = (
        f"/goal Complete Autopilot NodeKit task {task['id']} ({_clip(task.get('title'), 180)}). "
        f"Project goal: {_clip(project_goal, 260) or 'use automation/manifest.yml as source of truth'}. "
        f"Outcome: {_clip(task.get('objective'), 480)}. "
        f"Done when: {_clip(task.get('success_criteria'), 480)}. "
        f"Verify with {verifier_text}. "
        f"Current task status is {status}; use NodeKit as the durable outer loop, not ad-hoc state. "
        f"Before edits read AGENTS.md, automation/manifest.live.md, LOOP_STATE.md/PLANS.md, and run `python -m autopilot_nodekit memory-plan --workspace . --task-id {task['id']}`. "
        f"Work in small checkpoints: claim/run with `python -m autopilot_nodekit run-once --workspace . --worker-id {worker_id}` when using the controlled runner, or if editing directly, preserve the same worker_result.json contract. "
        f"After each attempt update LOOP_STATE.md or PLANS.md, preserve runs/ and memory/nodes/ evidence, and run `python -m autopilot_nodekit validate --workspace .`. "
        f"Never mark passed unless the verifier passes; verifier evidence overrides worker self-report. "
        f"If task_contract.review_policy.required is true, run Santa dual-review and include reviewer_a=NICE and reviewer_b=NICE in worker_result.json. "
        f"Use depends_on only for predecessors that must pass; use after_attempt for diagnostic bridge tasks after failed/blocked/skipped attempts."
        f"{required_bits} "
        f"Stop if the verifier cannot run, the next step is outside scope, repeated failures produce no new hypothesis, or missing input blocks honest progress; report evidence and the unblocker."
    )
    # Codex slash-command docs specify a 4,000 character goal objective limit. Keep
    # a conservative margin because some clients include command text in the count.
    if len(body) > 3900:
        body = body[:3898].rstrip() + "…"

    return {
        "task_id": task["id"],
        "goal": body,
        "length": len(body),
        "verifier": verifier,
        "task_status": status,
    }


def write_codex_goal_file(path: Path, result: dict[str, Any]) -> None:
    text = (
        "# Codex Goal\n\n"
        "Paste the command below into the Codex CLI, Codex app, or IDE composer.\n\n"
        "```text\n"
        f"{result['goal']}\n"
        "```\n\n"
        "## Metadata\n\n"
        f"- task_id: `{result['task_id']}`\n"
        f"- goal_length: `{result['length']}`\n"
        f"- verifier_source: `{result.get('verifier', {}).get('source')}`\n"
        f"- verifier_command: `{result.get('verifier', {}).get('command') or ''}`\n"
    )
    write_text(path, text)


def render_codex_goal(
    workspace: Path,
    db: AutoDB,
    task_id: str | None = None,
    *,
    include_slash_command: bool = True,
    max_chars: int = 4000,
) -> str:
    result = build_codex_goal(workspace, db, task_id=task_id)
    text = str(result["goal"])
    if not include_slash_command and text.startswith("/goal "):
        text = text[len("/goal "):]
    if len(text) > max_chars:
        suffix = "…"
        text = text[: max_chars - len(suffix)].rstrip() + suffix
    return text
