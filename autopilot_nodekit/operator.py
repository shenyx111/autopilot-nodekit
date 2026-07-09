from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, Optional

from .background import background_status, launch_background_worker
from .db import AutoDB
from .recovery import recover_stale_runs, resolve_by_repair
from .repair import add_repair_task
from .util import now_iso, read_json, workspace_paths
from .workflow import next_command


CONTROL_ACTION_PHASES = {
    "repair_required",
    "resolve_failed_task_by_passed_repair",
    "background_task_running_monitor_only",
    "finish_running_task",
    "execute_next_ready_task",
}

HUMAN_GATE_PHASES = {
    "0_combined_startup_review",
    "0_setup_files_skills_subagents_permissions",
    "1_review_task_list_and_plan",
    "3_pilot_review",
    "human_gate_pending",
    "human_or_unblock_required",
}


def operator_step(
    workspace: Path,
    db: AutoDB,
    *,
    worker_id: str = "codex-worker",
    stale_minutes: float = 30.0,
    max_auto_repair_depth: int = 3,
    start_background: bool = False,
    backend: Optional[str] = None,
) -> Dict[str, Any]:
    """Run one non-destructive supervisor/control-plane step.

    The operator is intentionally narrower than the worker. It does not do
    domain work. It only handles routine control-plane transitions that should
    not require the user to press the next-command button repeatedly:

    - create a focused repair task for failed work;
    - resolve a failed parent using a passed repair task;
    - recover an actually stale running run;
    - optionally launch a background worker when ready work exists but no worker
      appears to be active.

    Human gates and destructive/resource gates are never auto-approved here.
    """
    workspace = workspace.resolve()
    info = next_command(workspace, db)
    phase = str(info.get("phase") or "")
    report: Dict[str, Any] = {
        "ts": now_iso(),
        "phase": phase,
        "worker_id": worker_id,
        "action": "none",
        "reason": info.get("why", ""),
        "next_command": info,
    }

    if phase in HUMAN_GATE_PHASES:
        report.update({"action": "pause_for_human_gate", "handled": False})
        db.event("operator_paused_human_gate", report, task_id=info.get("task_id"), worker_id="operator")
        return report

    if phase == "repair_required":
        task_id = str(info.get("task_id") or "")
        attempts = _repair_attempt_count(db, task_id)
        if attempts >= max_auto_repair_depth:
            report.update({
                "action": "pause_repair_depth_limit",
                "handled": False,
                "task_id": task_id,
                "repair_attempts": attempts,
                "max_auto_repair_depth": max_auto_repair_depth,
            })
            db.event("operator_paused_repair_depth_limit", report, task_id=task_id, worker_id="operator")
            return report
        summary = _failure_summary(workspace, db, task_id)
        repair_id = add_repair_task(db, task_id, summary)
        report.update({"action": "add_repair_task", "handled": True, "task_id": task_id, "repair_task_id": repair_id, "summary": summary})
        db.event("operator_added_repair_task", report, task_id=repair_id, worker_id="operator")
        return report

    if phase == "resolve_failed_task_by_passed_repair":
        failed_task_id = str(info.get("task_id") or "")
        repair_task_id = str(info.get("repair_task_id") or "")
        result = resolve_by_repair(db, failed_task_id, repair_task_id, summary="Operator resolved failed task by passed repair evidence.")
        report.update({"action": "resolve_by_repair", "handled": True, "result": result})
        db.event("operator_resolved_by_repair", report, task_id=failed_task_id, worker_id="operator")
        return report

    if phase == "background_task_running_monitor_only":
        run_id = info.get("run_id")
        stale = recover_stale_runs(workspace, db, run_id=str(run_id), age_minutes=stale_minutes, mark_failed=True) if run_id else {"runs": []}
        item = (stale.get("runs") or [{}])[0]
        action = item.get("action") or "monitor"
        handled = action in {"marked_failed", "finish_recommended"}
        report.update({"action": "recover_stale" if handled else "monitor_running_background_task", "handled": handled, "stale_report": stale})
        db.event("operator_monitored_running_task", report, task_id=info.get("task_id"), run_id=str(run_id) if run_id else None, worker_id="operator")
        return report

    if phase == "finish_running_task":
        # Finish only when a result file exists. This avoids the premature-finish
        # issue seen with detached background workers.
        run_id = str(info.get("run_id") or "")
        paths = workspace_paths(workspace)
        result_path = paths["runs"] / run_id / "worker_result.json"
        if result_path.exists():
            from .runner import finish_prepared_codex_run

            status = finish_prepared_codex_run(workspace, db, run_id)
            report.update({"action": "finish_run_with_existing_worker_result", "handled": True, "run_id": run_id, "status": status})
            db.event("operator_finished_run", report, run_id=run_id, task_id=info.get("task_id"), worker_id="operator")
            return report
        report.update({"action": "monitor_no_worker_result_yet", "handled": False, "run_id": run_id, "result_path": str(result_path)})
        db.event("operator_refused_premature_finish", report, run_id=run_id, task_id=info.get("task_id"), worker_id="operator")
        return report

    if phase == "execute_next_ready_task":
        if start_background:
            status = background_status(workspace, worker_id=worker_id)
            heartbeat = status.get("heartbeat") or {}
            hb_pid = heartbeat.get("pid")
            if heartbeat and str(heartbeat.get("phase") or "") not in {"exited", "stopped_idle"}:
                report.update({"action": "background_already_active", "handled": False, "background_status": status})
                db.event("operator_background_already_active", report, task_id=info.get("task_id"), worker_id="operator")
                return report
            launched = launch_background_worker(workspace, worker_id=worker_id, max_cycles=0, backend=backend)
            report.update({"action": "launch_background_worker", "handled": True, "launch": launched})
            db.event("operator_launched_background", report, task_id=info.get("task_id"), worker_id="operator")
            return report
        report.update({"action": "ready_work_waiting_for_worker", "handled": False})
        db.event("operator_ready_work_waiting", report, task_id=info.get("task_id"), worker_id="operator")
        return report

    if phase == "complete_or_no_ready_work":
        report.update({"action": "complete_or_idle", "handled": False})
        db.event("operator_idle_or_complete", report, worker_id="operator")
        return report

    report.update({"action": "no_operator_rule", "handled": False})
    db.event("operator_no_rule", report, task_id=info.get("task_id"), worker_id="operator")
    return report


def operator_loop(
    workspace: Path,
    db: AutoDB,
    *,
    worker_id: str = "codex-worker",
    max_cycles: int = 0,
    sleep_seconds: int = 10,
    stale_minutes: float = 30.0,
    max_auto_repair_depth: int = 3,
    start_background: bool = False,
    backend: Optional[str] = None,
) -> int:
    cycles = 0
    while max_cycles <= 0 or cycles < max_cycles:
        operator_step(
            workspace,
            db,
            worker_id=worker_id,
            stale_minutes=stale_minutes,
            max_auto_repair_depth=max_auto_repair_depth,
            start_background=start_background,
            backend=backend,
        )
        cycles += 1
        time.sleep(sleep_seconds)
    return cycles


def _repair_attempt_count(db: AutoDB, failed_task_id: str) -> int:
    prefix = failed_task_id + "_REPAIR_"
    return sum(1 for t in db.list_tasks() if str(t["id"]).startswith(prefix))


def _failure_summary(workspace: Path, db: AutoDB, task_id: str) -> str:
    task = db.get_task(task_id)
    base = str(task["result_summary"] if task is not None and task["result_summary"] else "failed task needs focused repair")
    runs = db.list_runs(task_id)
    for run in runs:
        rid = run["run_id"]
        run_dir = workspace_paths(workspace)["runs"] / rid
        for name in ("control_result.json", "worker_result.normalized.json", "worker_result.json"):
            data = read_json(run_dir / name, default=None)
            if isinstance(data, dict):
                summary = data.get("summary") or (data.get("result") or {}).get("summary")
                failure = data.get("failure_reason") or (data.get("result") or {}).get("failure_reason")
                bits = [str(x) for x in (summary, failure) if x]
                if bits:
                    return " | ".join(bits)[:500]
    return base[:500]
