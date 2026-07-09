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

    # Mainline-first scheduling guard.
    #
    # Earlier versions scanned every historical failed task before considering
    # whether the current mainline had already moved on. In long repair chains
    # this could drag the operator back to an old failed repair task after F001
    # had already released F002. v0.9.3 only repairs/resolves failures that are
    # still on the active frontier: they block unreleased downstream tasks, or
    # they are the current leaf failure with no later mainline progress. Ready
    # work always wins over historical failed leftovers.
    if ready:
        task = ready[0]
        return {
            "phase": "execute_next_ready_task",
            "task_id": task["id"],
            "command": "python -m autopilot_nodekit codex-prepare --workspace . --worker-id codex-interactive",
            "why": f"Next ready task is {task['id']}: {task['title']}. In unattended mode, a background worker should claim this automatically; do not manually claim if a worker is healthy.",
        }

    actionable_failed, ignored_failed = _active_failed_tasks(db, tasks)

    for task in actionable_failed:
        repair = _passed_repair_for(task["id"], tasks)
        if repair:
            return {
                "phase": "resolve_failed_task_by_passed_repair",
                "task_id": task["id"],
                "repair_task_id": repair["id"],
                "command": f"python -m autopilot_nodekit resolve-by-repair --workspace . --failed-task-id {task['id']} --repair-task-id {repair['id']} --summary 'Resolved by passed repair evidence.'",
                "why": "A focused repair task has passed and the failed parent is still on the active frontier; resolve it and rewire blocked downstream gates.",
            }

    if actionable_failed:
        task = actionable_failed[0]
        return {
            "phase": "repair_required",
            "task_id": task["id"],
            "command": f"python -m autopilot_nodekit add-repair-task --workspace . --failed-task-id {task['id']} --summary '<failure reason>'",
            "why": "An active-frontier failed task needs a focused repair task or human decision. Historical failed tasks that no longer block mainline progress are ignored.",
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


def _active_failed_tasks(db: AutoDB, tasks: Dict[str, Dict[str, Any]]) -> tuple[list[Dict[str, Any]], list[Dict[str, Any]]]:
    failed = [t for t in tasks.values() if t.get("status") == "failed" and not t.get("superseded_by")]
    active: list[Dict[str, Any]] = []
    ignored: list[Dict[str, Any]] = []
    for task in sorted(failed, key=lambda t: (-int(t.get("priority") or 0), int(t.get("manifest_order") or 100000), str(t.get("id") or ""))):
        tid = str(task.get("id") or "")
        if _blocks_unreleased_downstream(db, tid, tasks):
            active.append(task)
            continue
        if _is_repair_task_id(tid):
            # A failed repair task that no longer gates downstream progress is
            # historical evidence, not the current mainline frontier.
            ignored.append(task)
            continue
        if _is_frontier_leaf_failure(task, tasks):
            active.append(task)
        else:
            ignored.append(task)
    return active, ignored


def _blocks_unreleased_downstream(db: AutoDB, task_id: str, tasks: Dict[str, Dict[str, Any]]) -> bool:
    for edge in db.list_edges(edge_type="depends_on") + db.list_edges(edge_type="after_attempt") + db.list_edges(edge_type="blocked_by"):
        if edge["to_task"] != task_id:
            continue
        downstream = tasks.get(edge["from_task"])
        if not downstream:
            continue
        # planned/blocked/review_pending downstream items still need this edge
        # to resolve. ready/running/passed/skipped/superseded have already moved
        # beyond it, so the failed task is not an active blocker.
        if downstream.get("status") in {"planned", "blocked", "review_pending"}:
            return True
    return False


def _is_frontier_leaf_failure(task: Dict[str, Any], tasks: Dict[str, Dict[str, Any]]) -> bool:
    order = int(task.get("manifest_order") or 100000)
    tid = str(task.get("id") or "")
    # If any later mainline task has already progressed, this failure is
    # historical and should not steal scheduler focus. Repair IDs are ignored
    # here because they are side-branches, not mainline milestones.
    for other in tasks.values():
        oid = str(other.get("id") or "")
        if oid == tid or _is_repair_task_id(oid):
            continue
        other_order = int(other.get("manifest_order") or 100000)
        if other_order > order and other.get("status") in {"ready", "running", "passed", "review_pending", "planned", "blocked"}:
            return False
    return True


def _is_repair_task_id(task_id: str) -> bool:
    return "_REPAIR_" in task_id


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
