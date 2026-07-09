from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .db import AutoDB
from .runner import finish_prepared_codex_run
from .util import now_iso, write_json, workspace_paths


def recover_stale_runs(
    workspace: Path,
    db: AutoDB,
    *,
    run_id: Optional[str] = None,
    age_minutes: float = 30.0,
    mark_failed: bool = False,
) -> Dict[str, Any]:
    """Inspect or recover stale running task runs.

    This is deliberately conservative. It does not guess domain success. It only
    turns an apparently abandoned running run into a failed evidence-bearing run
    when --mark-failed is explicit, so NodeKit can enter a repair loop instead of
    staying stuck forever.
    """
    paths = workspace_paths(workspace)
    candidates = []
    if run_id:
        run = db.get_run(run_id)
        if run is not None:
            candidates.append(run)
    else:
        candidates = [r for r in db.list_runs() if r["status"] == "running"]
    report: Dict[str, Any] = {"workspace": str(workspace.resolve()), "age_minutes": age_minutes, "mark_failed": mark_failed, "runs": [], "errors": []}
    cutoff = float(age_minutes) * 60.0
    for run in candidates:
        rid = run["run_id"]
        task_id = run["task_id"]
        run_dir = paths["runs"] / rid
        latest = _latest_mtime(run_dir)
        age = max(0.0, time.time() - latest) if latest else None
        result_exists = (run_dir / "worker_result.json").exists()
        control_exists = (run_dir / "control_result.json").exists()
        heartbeat = _read_worker_heartbeat(paths["automation"] / "background")
        active_by_heartbeat = bool(heartbeat.get("run_id") == rid and _pid_alive(heartbeat.get("pid")))
        item = {
            "run_id": rid,
            "task_id": task_id,
            "run_dir": str(run_dir),
            "latest_activity_seconds_ago": age,
            "worker_result_exists": result_exists,
            "control_result_exists": control_exists,
            "active_by_heartbeat": active_by_heartbeat,
            "action": "inspect",
            "reason": "not stale or needs explicit --mark-failed",
        }
        if result_exists and not control_exists:
            item.update({"action": "finish_recommended", "reason": "worker_result.json exists but control_result.json is missing; run codex-finish"})
        elif active_by_heartbeat:
            item.update({"action": "monitor", "reason": "background heartbeat says this run is still active"})
        elif age is not None and age >= cutoff and not result_exists:
            if mark_failed:
                write_json(
                    run_dir / "worker_result.json",
                    {
                        "status": "failed",
                        "summary": "Recovered stale running task as failed.",
                        "details": f"No worker_result.json was produced for at least {age_minutes} minutes; recover-stale marked this run failed so repair can proceed.",
                        "failure_reason": "stale_running_no_worker_result",
                        "responsible_files": [str(run_dir)],
                        "patch_summary": "No domain patch was made; control-plane stale run was converted into failed evidence.",
                        "review": {"policy": "santa_dual_review", "reviewer_a": {"agent": "autopilot-santa-reviewer-a", "status": "NICE", "summary": "Stale recovery evidence reviewed.", "evidence": [str(run_dir)]}, "reviewer_b": {"agent": "autopilot-santa-reviewer-b", "status": "NICE", "summary": "Stale recovery boundary reviewed.", "evidence": [str(run_dir)]}},
                    },
                )
                try:
                    status = finish_prepared_codex_run(workspace, db, rid, exit_code=1)
                    item.update({"action": "marked_failed", "reason": f"stale run converted to {status}"})
                except Exception as exc:
                    report["errors"].append({"run_id": rid, "error": str(exc)})
                    item.update({"action": "error", "reason": str(exc)})
            else:
                item.update({"action": "mark_failed_available", "reason": f"no worker_result.json and no active heartbeat for >= {age_minutes} minutes; rerun with --mark-failed to enter repair"})
        report["runs"].append(item)
    return report


def resolve_by_repair(db: AutoDB, failed_task_id: str, repair_task_id: str, *, summary: str = "Resolved by passed repair task.") -> Dict[str, Any]:
    failed = db.get_task(failed_task_id)
    repair = db.get_task(repair_task_id)
    if failed is None:
        raise KeyError(f"failed task not found: {failed_task_id}")
    if repair is None:
        raise KeyError(f"repair task not found: {repair_task_id}")
    if repair["status"] != "passed":
        raise ValueError(f"repair task must be passed, got {repair['status']}")
    rewired: List[Dict[str, str]] = []
    ts = now_iso()
    with db.transaction():
        downstream = list(db.conn.execute("SELECT from_task, edge_type FROM task_edges WHERE to_task=? AND edge_type IN ('depends_on','after_attempt','blocked_by')", (failed_task_id,)))
        for edge in downstream:
            db.conn.execute("DELETE FROM task_edges WHERE from_task=? AND to_task=? AND edge_type=?", (edge["from_task"], failed_task_id, edge["edge_type"]))
            db.conn.execute("INSERT OR IGNORE INTO task_edges(from_task,to_task,edge_type,created_at) VALUES(?,?,?,?)", (edge["from_task"], repair_task_id, edge["edge_type"], ts))
            rewired.append({"from_task": edge["from_task"], "old_to_task": failed_task_id, "new_to_task": repair_task_id, "edge_type": edge["edge_type"]})
        db.conn.execute(
            "UPDATE tasks SET status='superseded', superseded_by=?, result_summary=?, assigned_worker=NULL, lease_until=NULL, updated_at=? WHERE id=? AND status='failed'",
            (repair_task_id, summary, ts, failed_task_id),
        )
        db.event("task_resolved_by_repair", {"failed_task_id": failed_task_id, "repair_task_id": repair_task_id, "rewired_edges": rewired, "summary": summary}, task_id=failed_task_id)
        db.refresh_ready_tasks()
    return {"failed_task_id": failed_task_id, "repair_task_id": repair_task_id, "rewired_edges": rewired, "summary": summary}


def _latest_mtime(path: Path) -> Optional[float]:
    if not path.exists():
        return None
    latest = path.stat().st_mtime
    for root, _, files in os.walk(path):
        for name in files:
            try:
                latest = max(latest, (Path(root) / name).stat().st_mtime)
            except FileNotFoundError:
                pass
    return latest


def _read_worker_heartbeat(bg_dir: Path) -> Dict[str, Any]:
    latest: Dict[str, Any] = {}
    for path in bg_dir.glob("*.heartbeat.json"):
        try:
            import json
            data = json.loads(path.read_text(encoding="utf-8"))
            if not latest or str(data.get("ts", "")) > str(latest.get("ts", "")):
                latest = data
        except Exception:
            continue
    return latest


def _pid_alive(pid: Any) -> bool:
    try:
        pid_i = int(pid)
    except Exception:
        return False
    if pid_i <= 0:
        return False
    if os.name == "nt":
        # No hard dependency on tasklist privileges; unknown is treated as not active.
        return False
    try:
        os.kill(pid_i, 0)
        return True
    except OSError:
        return False
