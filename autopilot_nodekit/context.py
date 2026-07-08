from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List

from .db import AutoDB
from .util import load_yaml, write_json, write_text, workspace_paths
from .verifier import select_verifier


def build_context_pack(workspace: Path, db: AutoDB, task_id: str, run_id: str) -> Dict[str, Any]:
    paths = workspace_paths(workspace)
    task = db.get_task(task_id)
    if not task:
        raise ValueError(f"Task not found: {task_id}")
    config = load_yaml(paths["config"])
    deps = db.get_gating_dependency_tasks(task_id)
    memory_result = collect_memory_for_task(workspace, db, task_id, config=config)
    effective_verifier = effective_verifier_for_prompt(config, dict(task))
    task_contract = parse_json_field(task["task_contract_json"], default={}) if "task_contract_json" in task.keys() else {}

    pack = {
        "task": dict(task),
        "dependency_results": [dict(d) for d in deps],
        "effective_verifier": effective_verifier,
        "task_contract": task_contract,
        "memory_policy": {
            "non_lossy": True,
            "rule": "Do not overwrite or compress raw evidence. Structured memory nodes organize evidence and keep raw artifact paths.",
        },
        "memory_retrieval": memory_result["retrieval"],
        "retrieved_memory_nodes": memory_result["nodes"],
        "workspace": str(workspace),
        "run_id": run_id,
    }
    run_dir = paths["runs"] / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    write_json(run_dir / "memory_selection.json", memory_result)
    write_json(run_dir / "context_pack.json", pack)
    write_text(run_dir / "prompt.md", render_worker_prompt(pack, run_dir))
    db.update_run_paths(run_id, context_path=str(run_dir / "context_pack.json"), memory_selection_path=str(run_dir / "memory_selection.json"), prompt_path=str(run_dir / "prompt.md"))
    db.event(
        "memory_retrieved_for_task",
        {
            "loaded_count": len(memory_result["nodes"]),
            "stages": memory_result["retrieval"].get("stages", []),
            "unresolved_requirements": memory_result["retrieval"].get("unresolved_requirements", []),
        },
        task_id=task_id,
        run_id=run_id,
    )
    return pack


def collect_memory_for_task(workspace: Path, db: AutoDB, task_id: str, config: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """Return the exact memory nodes that should be injected for a task.

    This is intentionally not just a similarity search. It loads deterministic memory first
    from explicit IDs, previous attempts, parent chain, dependencies, after_attempt edges,
    same branch, required task IDs/tags/scopes, and only then uses FTS search as a supplement.
    """
    paths = workspace_paths(workspace)
    if config is None:
        config = load_yaml(paths["config"])
    task = db.get_task(task_id)
    if task is None:
        raise ValueError(f"Task not found: {task_id}")

    memory_cfg = config.get("memory", {}) or {}
    task_policy = parse_json_field(task["memory_policy_json"]) if "memory_policy_json" in task.keys() else {}
    if not isinstance(task_policy, dict):
        task_policy = {}

    search_limit = int(task_policy.get("search_limit") or memory_cfg.get("search_limit", 12))
    max_nodes_total = int(task_policy.get("max_nodes_total") or memory_cfg.get("max_nodes_total", 24))
    previous_attempt_limit = int(task_policy.get("previous_attempt_limit") or memory_cfg.get("previous_attempt_limit", 20))
    dependency_limit = int(task_policy.get("dependency_limit") or memory_cfg.get("dependency_limit", 40))
    after_attempt_limit = int(task_policy.get("after_attempt_limit") or memory_cfg.get("after_attempt_limit", dependency_limit))
    parent_limit = int(task_policy.get("parent_limit") or memory_cfg.get("parent_limit", 30))
    branch_limit = int(task_policy.get("branch_limit") or memory_cfg.get("branch_limit", 30))
    required_task_limit = int(task_policy.get("required_task_limit") or memory_cfg.get("required_task_limit", 60))
    tag_scope_limit = int(task_policy.get("tag_scope_limit") or memory_cfg.get("tag_scope_limit", 40))

    inject_full_nodes = bool(memory_cfg.get("inject_full_nodes", False))
    include_raw_artifacts = bool(memory_cfg.get("include_raw_artifact_paths", True))
    node_excerpt_lines = int(task_policy.get("node_excerpt_lines") or memory_cfg.get("node_excerpt_lines", 80))

    loaded: Dict[str, Dict[str, Any]] = {}
    order: List[str] = []
    stages: List[Dict[str, Any]] = []
    unresolved: List[str] = []
    omitted_due_to_limit = 0

    def add_rows(stage: str, rows: Iterable[Any], reason: str) -> None:
        nonlocal omitted_due_to_limit
        before = len(order)
        seen_in_stage = 0
        for row in rows:
            if row is None:
                continue
            seen_in_stage += 1
            node_id = row["id"]
            if node_id in loaded:
                if reason not in loaded[node_id]["retrieval_reasons"]:
                    loaded[node_id]["retrieval_reasons"].append(reason)
                continue
            if len(order) >= max_nodes_total:
                omitted_due_to_limit += 1
                continue
            rec = memory_row_to_record(
                row,
                inject_full_nodes=inject_full_nodes,
                include_raw_artifacts=include_raw_artifacts,
                node_excerpt_lines=node_excerpt_lines,
            )
            rec["retrieval_reasons"] = [reason]
            loaded[node_id] = rec
            order.append(node_id)
        stages.append({"stage": stage, "seen": seen_in_stage, "added": len(order) - before, "reason": reason})

    required_memory_ids = unique_strings(task_policy.get("required_memory_ids", []))
    if required_memory_ids and memory_cfg.get("include_explicit_required", True):
        rows = db.get_memory_by_ids(required_memory_ids)
        found_ids = {r["id"] for r in rows}
        for mid in required_memory_ids:
            if mid not in found_ids:
                unresolved.append(f"required_memory_id not found or inactive: {mid}")
        add_rows("required_memory_ids", rows, "explicit required_memory_ids in task.memory")

    if memory_cfg.get("include_previous_attempts", True):
        rows = db.list_memory_for_task_ids([task_id], limit=previous_attempt_limit)
        add_rows("previous_attempts", rows, f"previous memory from same task {task_id}")

    parent_ids = [p["id"] for p in db.get_parent_chain(task_id)]
    if parent_ids and memory_cfg.get("include_parent_chain", True):
        rows = db.list_memory_for_task_ids(parent_ids, limit=parent_limit)
        add_rows("parent_chain", rows, "memory from parent task chain: " + ", ".join(parent_ids))

    dep_ids = [d["id"] for d in db.get_dependency_tasks(task_id)]
    if dep_ids and memory_cfg.get("include_dependencies", True):
        rows = db.list_memory_for_task_ids(dep_ids, limit=dependency_limit)
        add_rows("dependencies", rows, "memory from depends_on tasks: " + ", ".join(dep_ids))

    after_ids = [e["to_task"] for e in db.list_edges(from_task=task_id, edge_type="after_attempt")]
    if after_ids and memory_cfg.get("include_after_attempt", True):
        rows = db.list_memory_for_task_ids(after_ids, limit=after_attempt_limit)
        add_rows("after_attempt", rows, "memory from after_attempt tasks: " + ", ".join(after_ids))

    branch_ids = [r["id"] for r in db.get_same_branch_tasks(task_id, limit=20)]
    if branch_ids and memory_cfg.get("include_same_branch_recent", True):
        rows = db.list_memory_for_task_ids(branch_ids, limit=branch_limit)
        add_rows("same_branch_recent", rows, "recent memory from same task branch: " + ", ".join(branch_ids))

    required_task_ids = unique_strings(task_policy.get("required_task_ids", []))
    if required_task_ids and memory_cfg.get("include_explicit_required", True):
        missing_tasks = [tid for tid in required_task_ids if db.get_task(tid) is None]
        for tid in missing_tasks:
            unresolved.append(f"required_task_id not found: {tid}")
        rows = db.list_memory_for_task_ids(required_task_ids, limit=required_task_limit)
        add_rows("required_task_ids", rows, "explicit required_task_ids in task.memory: " + ", ".join(required_task_ids))

    required_tags = unique_strings(task_policy.get("required_tags", []))
    required_scopes = unique_strings(task_policy.get("required_scopes", []))
    if (required_tags or required_scopes) and memory_cfg.get("include_required_tags_scopes", True):
        rows = db.list_memory_by_tags_scopes(required_tags, required_scopes, limit=tag_scope_limit, match_mode=str(task_policy.get("tag_match", "any")))
        reason_parts = []
        if required_tags:
            reason_parts.append("tags=" + ",".join(required_tags))
        if required_scopes:
            reason_parts.append("scopes=" + ",".join(required_scopes))
        add_rows("required_tags_scopes", rows, "explicit tag/scope selector: " + "; ".join(reason_parts))

    search_queries = unique_strings(task_policy.get("search_queries", []))
    if search_queries and memory_cfg.get("include_search_queries", True):
        for query in search_queries:
            rows = db.search_memory(query, search_limit)
            add_rows("explicit_search", rows, f"explicit search query: {query}")

    if memory_cfg.get("include_auto_fts", True):
        auto_query = " ".join([str(task["title"]), str(task["objective"]), str(task["success_criteria"])])
        rows = db.search_memory(auto_query, search_limit)
        add_rows("auto_fts", rows, "automatic FTS from task title/objective/success criteria")

    nodes = [loaded[nid] for nid in order]
    retrieval = {
        "strategy": "deterministic_task_graph_then_tags_then_search",
        "task_memory_policy": task_policy,
        "config_memory_policy": memory_cfg,
        "limits": {
            "max_nodes_total": max_nodes_total,
            "search_limit": search_limit,
            "previous_attempt_limit": previous_attempt_limit,
            "dependency_limit": dependency_limit,
            "after_attempt_limit": after_attempt_limit,
            "parent_limit": parent_limit,
            "branch_limit": branch_limit,
            "required_task_limit": required_task_limit,
            "tag_scope_limit": tag_scope_limit,
            "node_excerpt_lines": node_excerpt_lines,
        },
        "stages": stages,
        "loaded_node_ids": order,
        "loaded_count": len(nodes),
        "omitted_due_to_limit": omitted_due_to_limit,
        "unresolved_requirements": unresolved,
        "note": "Nodes are selected, not compressed. Raw evidence remains under runs/ and node files remain under memory/nodes/.",
    }
    return {"nodes": nodes, "retrieval": retrieval}


def memory_row_to_record(row: Any, inject_full_nodes: bool, include_raw_artifacts: bool, node_excerpt_lines: int = 80) -> Dict[str, Any]:
    content = row["content"]
    if not inject_full_nodes:
        content = first_lines(content, node_excerpt_lines)
    return {
        "id": row["id"],
        "title": row["title"],
        "scope": row["scope"],
        "tags": parse_json_field(row["tags_json"], default=[]),
        "content": content,
        "node_dir": row["node_dir"],
        "node_file": str(Path(row["node_dir"]) / "node.md") if row["node_dir"] else "",
        "raw_artifacts": parse_json_field(row["raw_artifacts_json"], default=[]) if include_raw_artifacts else [],
        "task_id": row["task_id"],
        "run_id": row["run_id"],
        "confidence": row["confidence"],
        "updated_at": row["updated_at"],
    }


def effective_verifier_for_prompt(config: Dict[str, Any], task: Dict[str, Any]) -> Dict[str, Any]:
    verifier = select_verifier(task, config)
    return {**verifier, "_source": verifier.get("source", "none")}


def parse_json_field(value: Any, default: Any = None) -> Any:
    if default is None:
        default = {}
    if value is None or value == "":
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(str(value))
    except Exception:
        return default


def unique_strings(items: Any) -> List[str]:
    if items is None:
        return []
    if isinstance(items, str):
        items = [items]
    out: List[str] = []
    for item in items:
        s = str(item).strip()
        if s and s not in out:
            out.append(s)
    return out


def first_lines(text: str, n: int) -> str:
    lines = text.splitlines()
    return "\n".join(lines[:n])


def render_worker_prompt(pack: Dict[str, Any], run_dir: Path) -> str:
    task = pack["task"]
    retrieval = pack.get("memory_retrieval", {})
    verifier = pack.get("effective_verifier", {})
    task_contract = pack.get("task_contract", {}) or {}
    lines = [
        "# Autopilot Worker Task",
        "",
        f"Task ID: `{task['id']}`",
        f"Run ID: `{pack['run_id']}`",
        "",
        "## Objective",
        task["objective"],
        "",
        "## Success criteria",
        task["success_criteria"],
        "",
        "## Task contract",
        json.dumps(task_contract, ensure_ascii=False, indent=2) if task_contract else "(no explicit task contract found; treat success criteria as mandatory)",
        "",
        "## Authoritative verifier",
        f"source: `{verifier.get('_source', 'none')}`",
        f"command: `{verifier.get('command', '') or '(none configured)'}`",
        "",
        "The verifier is authoritative. Do not report `passed` unless the code changes satisfy the success criteria and the configured verifier is expected to pass. Autopilot NodeKit will override a pass-like worker result to `failed` if the worker command or verifier exits non-zero.",
        "",
        "## Mandatory Santa dual-review",
        "If `task_contract.review_policy.required` is true, a pass-like result must include two independent review records. Use repo-local Codex subagents `autopilot-santa-reviewer-a` and `autopilot-santa-reviewer-b` when available, or run two separated checker passes with no shared assumptions. Both must return NICE. If either returns NAUGHTY, fix the issue, re-run verifier, and re-run fresh reviews before writing `passed`.",
        "",
        "Required review object for passed worker_result.json:",
        "```json",
        json.dumps({
            "review": {
                "policy": "santa_dual_review",
                "reviewer_a": {"agent": "autopilot-santa-reviewer-a", "status": "NICE", "summary": "Independent reviewer A evidence-backed approval.", "evidence": ["verifier.log"], "issues": []},
                "reviewer_b": {"agent": "autopilot-santa-reviewer-b", "status": "NICE", "summary": "Independent reviewer B evidence-backed approval.", "evidence": ["artifact path"], "issues": []},
                "fixes_after_review": []
            }
        }, ensure_ascii=False, indent=2),
        "```",
        "",
        "NodeKit will override `passed` to `failed` if a required Santa review is missing, malformed, or not NICE/NICE.",
        "",
        "## Codex-native loop hints",
        "- Treat this prompt as the concrete work item for the current Codex `exec` run.",
        "- If this task is broad, create or update `PLANS.md` / `LOOP_STATE.md` before editing and record each iteration's hypothesis, patch, verifier result, and next action.",
        "- For nontrivial patches, use explicit maker/checker separation, then Santa dual-review before writing a passed worker_result.json.",
        "- Repo-local Codex skills live under `.agents/skills`; use them when relevant rather than inventing a new workflow inside the turn.",
        "- Execute exactly one task per loop step: Plan → Act → Observe → Update State → Verify → Finish or Repair.",
        "- Update `LOOP_STATE.md`, the task evidence file, or a memory node after every meaningful attempt.",
        "",
        "## Memory policy — structured, non-lossy node memory",
        "Do not replace evidence with a short summary. Keep raw outputs/logs/diffs/transcripts as files. Create structured memory nodes that point to the raw evidence and capture reusable facts, decisions, commands, failure modes, and next-use cues.",
        "",
        "The context below was built by deterministic task-graph retrieval first, then tag/scope filters, then FTS search. A node may have several retrieval reasons.",
        "",
        "## Dependency / gate results",
    ]
    deps = pack.get("dependency_results", [])
    if deps:
        for dep in deps:
            edge_type = dep.get("edge_type", "depends_on")
            lines.append(f"- `{dep['id']}` via `{edge_type}`: {dep.get('status')} — {dep.get('result_summary') or ''}")
    else:
        lines.append("- None")

    lines += ["", "## Memory retrieval audit"]
    stages = retrieval.get("stages", [])
    if stages:
        for stage in stages:
            lines.append(f"- {stage.get('stage')}: saw {stage.get('seen')}, added {stage.get('added')} — {stage.get('reason')}")
    else:
        lines.append("- No retrieval stages were run.")
    unresolved = retrieval.get("unresolved_requirements", [])
    if unresolved:
        lines += ["", "### Unresolved memory requirements"]
        lines.extend(f"- {item}" for item in unresolved)
    if retrieval.get("omitted_due_to_limit"):
        lines.append(f"- omitted_due_to_limit: {retrieval.get('omitted_due_to_limit')}")

    lines += ["", "## Retrieved memory nodes"]
    memories = pack.get("retrieved_memory_nodes", [])
    if memories:
        for m in memories:
            lines += [
                f"### {m['id']} — {m['title']}",
                f"source_task: {m.get('task_id')}; source_run: {m.get('run_id')}",
                f"scope: {m['scope']}; tags: {', '.join(m.get('tags', []))}",
                "retrieval_reasons: " + " | ".join(m.get("retrieval_reasons", [])),
                f"node_file: {m.get('node_file') or ''}",
                "",
                m.get("content", ""),
                "",
                "Raw artifacts: " + (", ".join(m.get("raw_artifacts", [])) if m.get("raw_artifacts") else "(none listed)"),
                "",
            ]
    else:
        lines.append("No retrieved memory nodes yet.")
    lines += [
        "",
        "## Required output contract",
        f"Write `{run_dir / 'worker_result.json'}` before exiting.",
        "",
        "Minimal schema:",
        "```json",
        json.dumps({
            "status": "passed | failed | blocked | skipped",
            "summary": "One-line result for manifest.live.",
            "details": "Full details; do not omit relevant facts.",
            "failure_reason": "Required when status is failed or blocked.",
            "responsible_files": ["Required when repair is needed."],
            "patch_summary": "Required when files changed.",
            "verifier_output": "Required summary of command output or why verifier could not run.",
            "review": {
                "policy": "santa_dual_review",
                "reviewer_a": {"agent": "autopilot-santa-reviewer-a", "status": "NICE | NAUGHTY", "summary": "evidence-backed review", "evidence": ["path or command"], "issues": []},
                "reviewer_b": {"agent": "autopilot-santa-reviewer-b", "status": "NICE | NAUGHTY", "summary": "evidence-backed review", "evidence": ["path or command"], "issues": []},
                "fixes_after_review": []
            },
            "memory_nodes": [
                {
                    "title": "Reusable node title",
                    "scope": "project | module | task | tool | bug | decision",
                    "tags": ["tag1", "tag2"],
                    "content": "Structured, evidence-backed memory. Prefer complete details over compression.",
                    "raw_artifacts": ["relative/or/absolute/path"],
                    "confidence": 0.9,
                }
            ],
            "graph_patch": {
                "operations": [
                    {
                        "op": "add_task",
                        "task": {
                            "id": "T001.1",
                            "parent_id": task["id"],
                            "title": "Diagnostic bridge task",
                            "objective": "...",
                            "success_criteria": "...",
                            "after_attempt": [task["id"]],
                            "memory": {
                                "required_task_ids": [task["id"]],
                                "required_tags": ["relevant-tag"],
                                "search_queries": ["what this bridge task must remember"],
                            },
                            "priority": 95,
                        },
                    }
                ]
            },
        }, ensure_ascii=False, indent=2),
        "```",
        "",
        "Graph patch rules:",
        "- Use `depends_on` only when the predecessor must be `passed` before this task can run.",
        "- For diagnostic bridge tasks after a failed/blocked parent, use `after_attempt` plus `parent_id`; do not use `depends_on` on a task that may fail.",
        "- Use `blocked_by` when a task should stay blocked until another unblocker task passes, is skipped, or is superseded.",
        "- Put `memory.required_task_ids`, `memory.required_tags`, and `memory.search_queries` on inserted tasks when they must inherit specific nodes.",
        "- Use `supersede_task` to replace a future task whose direction is now wrong.",
        "- Use `update_task` only for small status/objective/success criteria edits; it can also update `memory`, `verifier`, and gate edges.",
        "- If verification fails, do not broad-rewrite. Record failure_reason, responsible_files, patch_summary, verifier_output, then make the smallest repair or insert a repair task.",
        "- If the same failure recurs or max_attempts is reached, block and request human input instead of infinite retry.",
        "- Never delete history; supersede instead.",
    ]
    return "\n".join(lines) + "\n"
