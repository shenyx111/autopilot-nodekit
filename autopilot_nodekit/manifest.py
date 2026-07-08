from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Dict, List

from .db import AutoDB
from .util import dump_yaml, load_yaml, workspace_paths


def install_initial_files(workspace: Path, manifest_path: Path | None = None, config_path: Path | None = None, force: bool = False) -> None:
    paths = workspace_paths(workspace)
    paths["automation"].mkdir(parents=True, exist_ok=True)
    paths["runs"].mkdir(parents=True, exist_ok=True)
    paths["memory_nodes"].mkdir(parents=True, exist_ok=True)

    if manifest_path:
        if force or not paths["manifest"].exists():
            shutil.copyfile(manifest_path, paths["manifest"])
    elif force or not paths["manifest"].exists():
        dump_yaml(paths["manifest"], default_manifest())

    if config_path:
        if force or not paths["config"].exists():
            shutil.copyfile(config_path, paths["config"])
    elif force or not paths["config"].exists():
        dump_yaml(paths["config"], default_config())


def default_manifest() -> Dict[str, Any]:
    return {
        "project": {"name": "autopilot-nodekit-project", "goal": "Replace this with your project goal."},
        "tasks": [
            {
                "id": "T001",
                "title": "Run project preflight",
                "objective": "Inspect the repository, identify setup commands, and run the smallest safe verification command.",
                "success_criteria": "A worker_result.json exists with status passed, or a graph_patch inserts a diagnostic bridge task using after_attempt.",
                "priority": 100,
                "max_attempts": 1,
                "verifier": {"command": "", "timeout_seconds": None},
                "memory": {
                    "required_tags": ["project", "setup", "entrypoint"],
                    "required_scopes": ["project", "tool", "decision", "bug"],
                    "search_queries": ["project setup command entrypoint verifier"],
                    "search_limit": 12,
                },
            },
            {
                "id": "T002",
                "title": "Implement first target change",
                "objective": "Use the memory nodes from T001 to perform the first real project change.",
                "success_criteria": "Verification passes and memory nodes record the changed files, commands, and evidence.",
                "depends_on": ["T001"],
                "priority": 90,
                "memory": {
                    "required_task_ids": ["T001"],
                    "required_tags": ["setup", "entrypoint", "verification"],
                    "required_scopes": ["tool", "decision", "bug"],
                    "search_queries": ["canonical setup command", "test command", "entrypoint"],
                    "search_limit": 20,
                },
            },
        ],
    }


def default_config() -> Dict[str, Any]:
    return {
        "worker": {
            "agent": "shell",
            "command": "python - <<'PY'\nimport json, os, pathlib\nrun_dir=pathlib.Path(os.environ['AUTOPILOT_RUN_DIR'])\ncontext=json.loads((run_dir/'context_pack.json').read_text(encoding='utf-8'))\nloaded=context.get('memory_retrieval',{}).get('loaded_count',0)\n(run_dir/'worker_result.json').write_text(json.dumps({'status':'passed','summary':f'Demo worker passed; loaded_memory_nodes={loaded}.','details':'Replace worker.command in automation/config.yml with the Codex invocation from examples/config.codex.yml. The prompt/context pack includes deterministic memory retrieval and an authoritative verifier contract.','memory_nodes':[{'title':'Demo node','scope':'task','tags':['demo','verification'],'content':f'This node proves the control plane can claim, build deterministic memory context, run, record, verify, and render. This task saw {loaded} prior memory nodes in its context pack. Raw evidence is retained in runs/.','raw_artifacts':['prompt.md','context_pack.json','memory_selection.json','stdout.log','stderr.log','worker_result.json','worker_result.normalized.json','control_result.json'],'confidence':0.9}]}, ensure_ascii=False, indent=2), encoding='utf-8')\nPY",
            "timeout_seconds": None,
        },
        "verifier": {
            "command": "",
            "timeout_seconds": None,
        },
        "memory": {
            "mode": "structured_non_lossy",
            "retrieval_strategy": "deterministic_task_graph_then_tags_then_search",
            "include_explicit_required": True,
            "include_previous_attempts": True,
            "include_parent_chain": True,
            "include_dependencies": True,
            "include_after_attempt": True,
            "include_same_branch_recent": True,
            "include_required_tags_scopes": True,
            "include_search_queries": True,
            "include_auto_fts": True,
            "max_nodes_total": 24,
            "previous_attempt_limit": 20,
            "dependency_limit": 40,
            "after_attempt_limit": 40,
            "parent_limit": 30,
            "branch_limit": 30,
            "required_task_limit": 60,
            "tag_scope_limit": 40,
            "search_limit": 12,
            "include_raw_artifact_paths": True,
            "inject_full_nodes": False,
            "node_excerpt_lines": 80,
        },
        "tmux": {
            "session_prefix": "autopilot",
            "default_cycles": 0,
            "sleep_seconds": 5,
        },
    }


def import_manifest(db: AutoDB, manifest_path: Path) -> Dict[str, Any]:
    data = load_yaml(manifest_path)
    tasks: List[Dict[str, Any]] = data.get("tasks", []) or []
    if not isinstance(tasks, list):
        raise ValueError("manifest.yml must contain tasks: list")
    with db.transaction():
        for idx, task in enumerate(tasks):
            if not isinstance(task, dict) or "id" not in task:
                raise ValueError(f"Task at index {idx} must be a mapping with id")
            db.upsert_task(task, idx)
        db.event("manifest_imported", {"path": str(manifest_path), "task_count": len(tasks)})
        db.refresh_ready_tasks()
    return data
