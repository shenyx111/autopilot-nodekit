from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any, Dict, Iterable, List

from .db import AutoDB
from .util import now_iso, read_text, slugify, write_json, write_text, workspace_paths


def create_memory_nodes_from_result(workspace: Path, db: AutoDB, task_id: str, run_id: str, result: Dict[str, Any], run_dir: Path) -> List[Dict[str, Any]]:
    paths = workspace_paths(workspace)
    nodes = result.get("memory_nodes") or []
    if not nodes:
        nodes = [default_node_from_result(result)]
    created: List[Dict[str, Any]] = []
    for idx, node in enumerate(nodes, start=1):
        if not isinstance(node, dict):
            continue
        title = node.get("title") or f"{task_id} memory node {idx}"
        node_id = node.get("id") or f"M-{task_id}-{run_id[-8:]}-{idx:02d}-{uuid.uuid4().hex[:4]}"
        node_dir = paths["memory_nodes"] / node_id
        node_dir.mkdir(parents=True, exist_ok=True)
        raw_artifacts = normalize_artifacts(node.get("raw_artifacts", []), run_dir)
        raw_artifacts += [
            str(run_dir / "prompt.md"),
            str(run_dir / "context_pack.json"),
            str(run_dir / "memory_selection.json"),
            str(run_dir / "stdout.log"),
            str(run_dir / "stderr.log"),
            str(run_dir / "transcript.log"),
            str(run_dir / "worker_result.json"),
            str(run_dir / "worker_result.normalized.json"),
            str(run_dir / "control_result.json"),
        ]
        for optional_name in ("verifier.log", "worker_result.invalid.json", "graph_patch.json", "codex_final.md"):
            optional_path = run_dir / optional_name
            if optional_path.exists():
                raw_artifacts.append(str(optional_path))
        raw_artifacts = sorted(dict.fromkeys(raw_artifacts))
        content = render_node_markdown(
            node_id=node_id,
            task_id=task_id,
            run_id=run_id,
            title=title,
            scope=node.get("scope", "task"),
            tags=node.get("tags", []),
            content=node.get("content", result.get("details") or result.get("summary") or ""),
            raw_artifacts=raw_artifacts,
            result=result,
        )
        write_text(node_dir / "node.md", content)
        meta = {
            "id": node_id,
            "task_id": task_id,
            "run_id": run_id,
            "title": title,
            "scope": node.get("scope", "task"),
            "tags": node.get("tags", []),
            "confidence": float(node.get("confidence", 0.7)),
            "raw_artifacts": raw_artifacts,
            "created_at": now_iso(),
            "non_lossy": True,
        }
        write_json(node_dir / "metadata.json", meta)
        db_node = {
            **meta,
            "node_dir": str(node_dir),
            "content": content,
            "status": "active",
        }
        db.add_memory_node(db_node)
        db.event("memory_node_created", {"node_id": node_id, "title": title}, task_id=task_id, run_id=run_id)
        created.append(db_node)
    return created


def default_node_from_result(result: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "title": "Task result node",
        "scope": "task",
        "tags": ["auto", result.get("status", "unknown")],
        "content": result.get("details") or result.get("summary") or "No details supplied by worker.",
        "confidence": 0.6,
    }


def normalize_artifacts(items: Iterable[Any], run_dir: Path) -> List[str]:
    out: List[str] = []
    for item in items:
        if item is None:
            continue
        s = str(item)
        if not s:
            continue
        out.append(s)
    return out


def render_node_markdown(node_id: str, task_id: str, run_id: str, title: str, scope: str, tags: List[str], content: str, raw_artifacts: List[str], result: Dict[str, Any]) -> str:
    return f"""# {title}

- node_id: `{node_id}`
- task_id: `{task_id}`
- run_id: `{run_id}`
- scope: `{scope}`
- tags: {', '.join(tags) if tags else '(none)'}
- status_from_worker: `{result.get('status', 'unknown')}`
- created_at: `{now_iso()}`
- memory_policy: `structured_non_lossy`

## Reusable memory

{content.strip()}

## Worker summary

{result.get('summary', '').strip()}

## Worker details

{result.get('details', '').strip()}

## Evidence and raw artifacts

The following artifacts are retained as first-class evidence. This node organizes them; it does not replace them.

""" + "\n".join(f"- `{p}`" for p in raw_artifacts) + "\n\n## Next-use cues\n\n- When a future task touches the same module/tool/failure mode, load this node and inspect the raw artifacts if any detail matters.\n- If a future run contradicts this node, create a new node and mark this one superseded instead of editing history.\n"
