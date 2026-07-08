from __future__ import annotations

from pathlib import Path
from typing import List

from .db import AutoDB, GATING_EDGE_TYPES
from .util import now_iso, write_text, workspace_paths


def render_live_manifest(workspace: Path, db: AutoDB) -> None:
    paths = workspace_paths(workspace)
    tasks = db.list_tasks()
    header = ["id", "status", "attempts", "parent", "gates", "title", "last_result", "next_action", "updated_at"]
    rows: List[List[str]] = []
    for t in tasks:
        gates = db.conn.execute(
            "SELECT to_task, edge_type FROM task_edges WHERE from_task=? AND edge_type IN ('depends_on','after_attempt','blocked_by') ORDER BY edge_type,to_task",
            (t["id"],),
        ).fetchall()
        gates_s = ",".join(f"{g['edge_type']}:{g['to_task']}" for g in gates) or "-"
        next_action = infer_next_action(db, t["id"], t["status"])
        rows.append([
            t["id"], t["status"], str(t["attempt_count"] or 0), t["parent_id"] or "", gates_s,
            t["title"], (t["result_summary"] or "").replace("\n", " ")[:160], next_action, t["updated_at"],
        ])
    tsv = "\t".join(header) + "\n" + "\n".join("\t".join(row) for row in rows) + "\n"
    write_text(paths["live_tsv"], tsv)

    lines = [
        "# Autopilot Live Manifest",
        "",
        f"Updated: {now_iso()}",
        "",
        "| id | status | attempts | parent | gates | title | last result | next action |",
        "|---|---:|---:|---|---|---|---|---|",
    ]
    for row in rows:
        lines.append("| " + " | ".join(escape_md(x) for x in row[:-1]) + " |")
    lines += ["", "## Active memory nodes", ""]
    memories = db.list_memory(50)
    if memories:
        lines.append("| id | scope | tags | title | evidence |")
        lines.append("|---|---|---|---|---|")
        for m in memories:
            lines.append(f"| {escape_md(m['id'])} | {escape_md(m['scope'])} | {escape_md(m['tags_json'])} | {escape_md(m['title'])} | {escape_md(m['node_dir'])} |")
    else:
        lines.append("No memory nodes yet.")
    write_text(paths["live_md"], "\n".join(lines) + "\n")


def infer_next_action(db: AutoDB, task_id: str, status: str) -> str:
    if status == "passed":
        children = db.conn.execute(
            "SELECT from_task, edge_type FROM task_edges WHERE to_task=? AND edge_type IN ('depends_on','after_attempt','blocked_by') ORDER BY edge_type,from_task",
            (task_id,),
        ).fetchall()
        if children:
            return "release/check: " + ",".join(f"{c['edge_type']}:{c['from_task']}" for c in children)
        return "done"
    if status == "failed":
        children = db.conn.execute("SELECT from_task FROM task_edges WHERE to_task=? AND edge_type='after_attempt' ORDER BY from_task", (task_id,)).fetchall()
        if children:
            return "after_attempt released: " + ",".join(c["from_task"] for c in children)
        return "needs graph_patch / diagnostic child"
    if status == "blocked":
        if db.has_gating_edges(task_id):
            return "waiting on gates"
        return "human decision or unblock patch"
    if status == "review_pending":
        return "human approval required"
    if status == "ready":
        return "claimable"
    if status == "running":
        return "worker active"
    if status == "planned":
        return "waiting on gates" if db.has_gating_edges(task_id) else "ready on refresh"
    return "none"


def escape_md(value: str) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")
