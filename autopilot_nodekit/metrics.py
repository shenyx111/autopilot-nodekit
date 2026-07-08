from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from .db import AutoDB
from .util import write_json, write_text, workspace_paths


def compute_metrics(workspace: Path, db: AutoDB) -> Dict[str, Any]:
    tasks = [dict(t) for t in db.list_tasks()]
    runs = [dict(r) for r in db.list_runs()]
    status_counts: Dict[str, int] = {}
    for task in tasks:
        status_counts[task["status"]] = status_counts.get(task["status"], 0) + 1
    attempts = [int(t.get("attempt_count") or 0) for t in tasks]
    failed = [t for t in tasks if t["status"] == "failed"]
    blocked = [t for t in tasks if t["status"] == "blocked"]
    passed = [t for t in tasks if t["status"] == "passed"]
    total = len(tasks)
    events_path = workspace_paths(workspace)["events"]
    event_counts: Dict[str, int] = {}
    rejection_count = 0
    santa_override_count = 0
    if events_path.exists():
        for line in events_path.read_text(encoding="utf-8").splitlines():
            try:
                evt = json.loads(line)
            except Exception:
                continue
            et = str(evt.get("event_type") or "")
            event_counts[et] = event_counts.get(et, 0) + 1
            if et == "human_rejected_task":
                rejection_count += 1
            payload = evt.get("payload") if isinstance(evt.get("payload"), dict) else {}
            if "Santa dual-review failed" in str(payload.get("summary", "")):
                santa_override_count += 1
    failure_summaries = []
    for task in failed[:20] + blocked[:20]:
        failure_summaries.append({
            "task_id": task["id"],
            "status": task["status"],
            "attempts": task.get("attempt_count"),
            "summary": task.get("result_summary"),
        })
    return {
        "task_count": total,
        "status_counts": status_counts,
        "passed_ratio": (len(passed) / total) if total else 0.0,
        "failed_count": len(failed),
        "blocked_count": len(blocked),
        "human_rejection_count": rejection_count,
        "santa_review_override_count": santa_override_count,
        "average_attempts_per_task": (sum(attempts) / total) if total else 0.0,
        "max_attempts_seen": max(attempts) if attempts else 0,
        "run_count": len(runs),
        "event_counts": event_counts,
        "failure_summaries": failure_summaries,
    }


def write_metrics_report(workspace: Path, db: AutoDB) -> Dict[str, Any]:
    paths = workspace_paths(workspace)
    metrics = compute_metrics(workspace, db)
    write_json(paths["automation"] / "metrics.json", metrics)
    lines = [
        "# Autopilot Metrics",
        "",
        f"- task_count: `{metrics['task_count']}`",
        f"- run_count: `{metrics['run_count']}`",
        f"- passed_ratio: `{metrics['passed_ratio']:.3f}`",
        f"- average_attempts_per_task: `{metrics['average_attempts_per_task']:.3f}`",
        f"- max_attempts_seen: `{metrics['max_attempts_seen']}`",
        f"- human_rejection_count: `{metrics['human_rejection_count']}`",
        f"- santa_review_override_count: `{metrics['santa_review_override_count']}`",
        "",
        "## Status counts",
        "",
    ]
    for status, count in sorted(metrics["status_counts"].items()):
        lines.append(f"- {status}: {count}")
    lines += ["", "## Top failures / blockers", ""]
    for item in metrics["failure_summaries"]:
        lines.append(f"- `{item['task_id']}` {item['status']} attempts={item['attempts']}: {item.get('summary') or ''}")
    if not metrics["failure_summaries"]:
        lines.append("- none")
    write_text(paths["automation"] / "metrics.md", "\n".join(lines) + "\n")
    return metrics
