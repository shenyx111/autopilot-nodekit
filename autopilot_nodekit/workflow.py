from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from .db import AutoDB


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
            "why": "No task graph exists. Use smart-start so missing gate_mode/task_scale/artifact_count/journal settings are asked before PROJECT_SPEC.yml, contract, manifest, and Codex-native files are generated.",
        }

    gstart = tasks.get("G000_START_REVIEW")
    if gstart and gstart["status"] == "review_pending":
        return {
            "phase": "0_combined_startup_review",
            "command": "python -m autopilot_nodekit approve-start --workspace . --summary 'Project spec, Layer 0 setup, contract, task manifest, permissions, and loop mode reviewed.'",
            "why": "Combined startup review is pending. Read PROJECT_SPEC.md, SETUP_REVIEW.md, GOAL_CONTRACT.md, TASK_REVIEW.md, REQUIREMENTS_LOCK.md, AGENTS.md, .agents/skills, and .codex/agents. This is the only manual stop in fast mode.",
        }

    g000 = tasks.get("G000_SETUP_REVIEW")
    if g000 and g000["status"] == "review_pending":
        return {
            "phase": "0_setup_files_skills_subagents_permissions",
            "command": "python -m autopilot_nodekit approve-setup --workspace . --summary 'Layer 0 files, skills, subagents, permissions, and verifier reviewed.'",
            "why": "Layer 0 setup gate is pending. Read PROJECT_SETUP.yml, SETUP_REVIEW.md, AGENTS.md, .agents/skills, and .codex/agents first.",
        }

    h000 = tasks.get("H000_PLAN_REVIEW")
    if h000 and h000["status"] == "review_pending":
        return {
            "phase": "1_review_task_list_and_plan",
            "command": "python -m autopilot_nodekit approve-plan --workspace . --summary 'Plan, contract, task count, gates, permissions, and Santa review policy reviewed.'",
            "why": "Plan review gate is pending. Read GOAL_CONTRACT.md, TASK_REVIEW.md, REQUIREMENTS_LOCK.md, automation/manifest.live.md first.",
        }

    if running:
        run = _latest_running_run(db, running[0]["id"])
        run_id = run["run_id"] if run else "<RUN_ID>"
        return {
            "phase": "finish_running_task",
            "task_id": running[0]["id"],
            "command": f"python -m autopilot_nodekit codex-finish --workspace . --run-id {run_id}",
            "why": "A task is already running. Finish it before claiming another task.",
        }

    h020 = tasks.get("H020_PILOT_REVIEW")
    if h020 and h020["status"] == "review_pending" and tasks.get("F001_QC", {}).get("status") == "passed":
        return {
            "phase": "3_pilot_review",
            "command": "python -m autopilot_nodekit approve-pilot --workspace . --summary 'Figure 001 reviewed for journal fit and approved for bulk loop.'",
            "why": "First figure QC passed; gate_mode requires human pilot review before F002+ releases.",
        }

    if ready:
        task = ready[0]
        return {
            "phase": "execute_next_ready_task",
            "task_id": task["id"],
            "command": "python -m autopilot_nodekit codex-prepare --workspace . --worker-id codex-interactive",
            "why": f"Next ready task is {task['id']}: {task['title']}. Finished pass results must include verifier evidence and Santa NICE/NICE review.",
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
    return "\n".join(lines) + "\n"
