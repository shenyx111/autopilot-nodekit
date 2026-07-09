from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from .db import AutoDB
from .util import workspace_paths


def next_command(workspace: Path, db: AutoDB) -> Dict[str, Any]:
    db.refresh_ready_tasks()
    tasks = {t["id"]: dict(t) for t in db.list_tasks()}
    running = [t for t in tasks.values() if t["status"] == "running"]
    ready = [t for t in tasks.values() if t["status"] == "ready"]
    review_pending = [t for t in tasks.values() if t["status"] == "review_pending"]
    failed = [t for t in tasks.values() if t["status"] == "failed"]
    blocked = [t for t in tasks.values() if t["status"] == "blocked"]

    if not tasks:
        return {
            "phase": "not_initialized",
            "command": "python -m autopilot_nodekit smart-start --workspace . --prompt-file PROJECT_PROMPT.md --force-codex-native",
            "why": "No task graph exists. Use smart-start so missing gate_mode/task_scale/artifact_count/project settings are asked before PROJECT_SPEC.yml, contract, manifest, and Codex-native files are generated.",
        }

    gstart = tasks.get("G000_START_REVIEW")
    if gstart and gstart["status"] == "review_pending":
        return {
            "phase": "0_combined_startup_review",
            "command": "python -m autopilot_nodekit approve-start --workspace . --summary 'Project spec, Layer 0 setup, contract, task manifest, permissions, and loop mode reviewed.'",
            "why": "Combined startup review is pending. Read PROJECT_SPEC.md, SETUP_REVIEW.md, GOAL_CONTRACT.md, TASK_REVIEW.md, REQUIREMENTS_LOCK.md, AGENTS.md, .agents/skills, .codex/agents, and .nodekit wrapper files first.",
        }

    g000 = tasks.get("G000_SETUP_REVIEW")
    if g000 and g000["status"] == "review_pending":
        return {
            "phase": "0_setup_files_skills_subagents_permissions",
            "command": "python -m autopilot_nodekit approve-setup --workspace . --summary 'Layer 0 files, skills, subagents, permissions, and verifier reviewed.'",
            "why": "Layer 0 setup gate is pending. Read PROJECT_SETUP.yml, SETUP_REVIEW.md, AGENTS.md, .agents/skills, .codex/agents, and .nodekit wrappers first.",
        }

    h000 = tasks.get("H000_PLAN_REVIEW")
    if h000 and h000["status"] == "review_pending":
        return {
            "phase": "1_review_task_list_and_plan",
            "command": "python -m autopilot_nodekit approve-plan --workspace . --summary 'Plan, contract, task count, gates, permissions, and Santa review policy reviewed.'",
            "why": "Plan review gate is pending. Read GOAL_CONTRACT.md, TASK_REVIEW.md, REQUIREMENTS_LOCK.md, and automation/manifest.live.md first.",
        }

    if running:
        task = running[0]
        run = _latest_running_run(db, task["id"])
        run_id = run["run_id"] if run else "<RUN_ID>"
        agent = str((run or {}).get("agent") or "")
        run_dir = workspace_paths(workspace)["runs"] / run_id if run else None
        worker_result_exists = bool(run_dir and (run_dir / "worker_result.json").exists())
        control_result_exists = bool(run_dir and (run_dir / "control_result.json").exists())
        if agent == "codex-interactive" or worker_result_exists:
            return {
                "phase": "finish_running_task",
                "task_id": task["id"],
                "run_id": run_id,
                "command": f"python -m autopilot_nodekit codex-finish --workspace . --run-id {run_id}",
                "why": "A running interactive/prepared task has a run to finish. Only run this after worker_result.json exists, or when explicitly recovering an abandoned prepared task.",
            }
        return {
            "phase": "background_task_running_monitor_only",
            "task_id": task["id"],
            "run_id": run_id,
            "command": "python -m autopilot_nodekit background-status --workspace . --worker-id codex-worker",
            "why": "A background/detached worker appears to own this task. Do not run codex-finish while the background worker may still be executing; monitor heartbeat/events. If it is stale, use recover-stale, not manual finish.",
        }

    h020 = tasks.get("H020_PILOT_REVIEW")
    if h020 and h020["status"] == "review_pending" and tasks.get("F001_QC", {}).get("status") == "passed":
        return {
            "phase": "3_pilot_review",
            "command": "python -m autopilot_nodekit approve-pilot --workspace . --summary 'Pilot artifact/workflow stage reviewed and approved for bulk loop.'",
            "why": "First pilot QC passed; gate_mode requires human pilot review before F002+ releases.",
        }

    # Prefer resolving failed tasks that already have a passed repair child.
    for task in failed:
        repair = _passed_repair_for(task["id"], tasks)
        if repair:
            return {
                "phase": "resolve_failed_task_by_passed_repair",
                "task_id": task["id"],
                "repair_task_id": repair["id"],
                "command": f"python -m autopilot_nodekit resolve-by-repair --workspace . --failed-task-id {task['id']} --repair-task-id {repair['id']} --summary 'Resolved by passed repair evidence.'",
                "why": "A focused repair task has passed; resolve the failed parent and rewire downstream gates to the repair evidence instead of nesting repairs forever.",
            }

    if ready:
        task = ready[0]
        return {
            "phase": "execute_next_ready_task",
            "task_id": task["id"],
            "command": "python -m autopilot_nodekit codex-prepare --workspace . --worker-id codex-interactive",
            "why": f"Next ready task is {task['id']}: {task['title']}. In unattended mode, a background worker should claim this automatically; do not manually claim if a worker is healthy.",
        }

    if failed:
        task = failed[0]
        return {
            "phase": "repair_required",
            "task_id": task["id"],
            "command": f"python -m autopilot_nodekit add-repair-task --workspace . --failed-task-id {task['id']} --summary '<failure reason>'",
            "why": "A failed task needs a focused repair task or human decision.",
        }

    if blocked:
        task = blocked[0]
        return {
            "phase": "human_or_unblock_required",
            "task_id": task["id"],
            "command": f"python -m autopilot_nodekit review-task --workspace . --task-id {task['id']}",
            "why": "A blocked task requires human review or an unblock/repair patch.",
        }

    if review_pending:
        task = review_pending[0]
        return {
            "phase": "human_gate_pending",
            "task_id": task["id"],
            "command": f"python -m autopilot_nodekit approve-task --workspace . --task-id {task['id']} --summary 'Reviewed and approved.'",
            "why": "A review gate is pending.",
        }

    return {
        "phase": "complete_or_no_ready_work",
        "command": "python -m autopilot_nodekit metrics --workspace .",
        "why": "No ready/running/failed/blocked/review-pending task remains. Generate metrics/final report.",
    }


def _latest_running_run(db: AutoDB, task_id: str) -> Optional[Dict[str, Any]]:
    runs = db.list_runs(task_id)
    for run in runs:
        if run["status"] == "running":
            return dict(run)
    return None


def _passed_repair_for(task_id: str, tasks: Dict[str, Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    prefix = task_id + "_REPAIR_"
    repairs = [t for tid, t in tasks.items() if tid.startswith(prefix) and t.get("status") == "passed"]
    if not repairs:
        return None
    return sorted(repairs, key=lambda t: len(t["id"]), reverse=True)[0]


def format_next_command(info: Dict[str, Any]) -> str:
    lines = [
        f"phase: {info.get('phase')}",
        f"why: {info.get('why')}",
        "",
        "RUN THIS:",
        info.get("command", ""),
    ]
    if info.get("task_id"):
        lines.insert(1, f"task_id: {info['task_id']}")
    if info.get("repair_task_id"):
        lines.insert(2, f"repair_task_id: {info['repair_task_id']}")
    if info.get("run_id"):
        lines.insert(2, f"run_id: {info['run_id']}")
    return "\n".join(lines) + "\n"
