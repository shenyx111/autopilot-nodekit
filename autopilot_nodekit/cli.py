from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any

from .codex_native import install_codex_native_files
from .codex_goal import build_codex_goal, write_codex_goal_file
from .context import collect_memory_for_task
from .artifact_verify import verify_artifact
from .figure_plan import generate_journal_figure_manifest, write_figure_manifest, write_review_files
from .workflow_plan import generate_workflow_manifest, write_project_manifest
from .setup_config import load_project_setup, render_setup_review, validate_project_setup
from .goal_contract import build_figure_goal_contract, load_goal_contract, write_goal_contract, render_goal_contract_review, validate_goal_contract, ensure_memory_dirs

from .project_spec import (
    build_codex_spec_goal,
    infer_project_spec_from_prompt,
    load_project_spec,
    prepare_codex_spec_draft,
    project_spec_path,
    spec_to_figure_plan_kwargs,
    spec_to_workflow_plan_kwargs,
    write_project_spec,
)
from .db import AutoDB, GATING_EDGE_TYPES
from .graph_patch import apply_graph_patch, load_patch
from .manifest import import_manifest, install_initial_files
from .render import render_live_manifest
from .runner import finish_prepared_codex_run, prepare_interactive_codex_run, run_once, worker_loop
from .metrics import write_metrics_report
from .workflow import next_command as compute_next_command, format_next_command
from .repair import add_repair_task
from .tmux import launch_tmux_worker
from .background import detect_background_backends, launch_background_worker
from .bootstrap import install_nodekit_runtime, worker_command_for_platform, nodekit_command_for_platform
from .smart_start import (
    TASK_SCALE_TO_TASKS_PER_FIGURE,
    analyze_start_prompt,
    build_spec_from_resolved,
    load_start_answers,
    normalize_task_scale,
    write_start_questions,
)
from .util import dump_yaml, load_yaml, render_table, workspace_paths
from .shell_safety import lint_shell_command, render_findings, should_block
from .operator import operator_step, operator_loop


def default_interactive_codex_config() -> dict[str, Any]:
    return {
        "worker": {"agent": "codex-cli", "command": worker_command_for_platform(), "timeout_seconds": None},
        "verifier": {"command": "", "timeout_seconds": None},
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
        "tmux": {"session_prefix": "autopilot-codex", "default_cycles": 100, "sleep_seconds": 10},
    }


def ensure_default_config(paths: dict[str, Path]) -> None:
    install_nodekit_runtime(paths["workspace"], force=True)
    paths["automation"].mkdir(parents=True, exist_ok=True)
    if not paths["config"].exists():
        dump_yaml(paths["config"], default_interactive_codex_config())
        return
    # Upgrade old interactive/demo configs that had worker.command: ''.
    try:
        cfg = load_yaml(paths["config"])
    except Exception:
        return
    worker = cfg.setdefault("worker", {})
    changed = False
    if not str(worker.get("command") or "").strip():
        worker["agent"] = "codex-cli"
        worker["command"] = worker_command_for_platform(paths["workspace"])
        worker["timeout_seconds"] = None
        changed = True
    if changed:
        dump_yaml(paths["config"], cfg)

def manifest_from_project_spec(spec: dict[str, Any]) -> dict[str, Any]:
    project_type = str(((spec.get("project") or {}).get("type")) or "journal_figures")
    if project_type == "journal_figures":
        return generate_journal_figure_manifest(**spec_to_figure_plan_kwargs(spec))
    return generate_workflow_manifest(**spec_to_workflow_plan_kwargs(spec))


def write_manifest_for_project(workspace: Path, manifest: dict[str, Any], spec: dict[str, Any]) -> None:
    project_type = str(((manifest.get("project") or {}).get("plan_type")) or "journal_figures")
    if project_type == "journal_figures":
        write_figure_manifest(workspace, manifest)
    else:
        write_project_manifest(workspace, manifest, spec=spec)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="autopilot-nodekit",
        description="Codex-native durable task graph + non-lossy memory control plane.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("init", help="Create automation/, DB, manifest, config, memory/, runs/.")
    p.add_argument("--workspace", default=".")
    p.add_argument("--manifest", type=Path)
    p.add_argument("--config", type=Path)
    p.add_argument("--force", action="store_true")
    p.add_argument("--codex-native", action="store_true", help="Also install AGENTS.md, .agents/skills, PLANS.md, LOOP_STATE.md, and .codex files.")

    p = sub.add_parser("install-codex-native", help="Install Codex-native AGENTS.md, .agents/skills, PLANS.md, LOOP_STATE.md, and .codex config/agents/hooks.")
    p.add_argument("--workspace", default=".")
    p.add_argument("--force", action="store_true")

    p = sub.add_parser("import-manifest", help="Import automation/manifest.yml into SQLite task graph.")
    p.add_argument("--workspace", default=".")
    p.add_argument("--manifest", type=Path)

    p = sub.add_parser("status", help="Show compact task status.")
    p.add_argument("--workspace", default=".")

    p = sub.add_parser("render", help="Render manifest.live.md and manifest.live.tsv.")
    p.add_argument("--workspace", default=".")

    p = sub.add_parser("validate", help="Validate task graph integrity, contract, gates, and reachability.")
    p.add_argument("--workspace", default=".")
    p.add_argument("--json", action="store_true")
    p.add_argument("--strict", action="store_true", help="Require GOAL_CONTRACT.yml and per-task verifiable contract fields.")

    p = sub.add_parser("claim", help="Claim one ready task without running it, for debugging.")
    p.add_argument("--workspace", default=".")
    p.add_argument("--worker-id", required=True)
    p.add_argument("--lease-seconds", type=int, default=0)

    p = sub.add_parser("run-once", help="Claim and run one ready task.")
    p.add_argument("--workspace", default=".")
    p.add_argument("--worker-id", required=True)
    p.add_argument("--lease-seconds", type=int, default=0)

    p = sub.add_parser("worker-loop", help="Run repeated claim/run/render cycles. By default it also runs the non-human operator loop for repair/recover/resolve transitions.")
    p.add_argument("--workspace", default=".")
    p.add_argument("--worker-id", required=True)
    p.add_argument("--max-cycles", type=int, default=0, help="0 means unlimited cycles; no NodeKit wall-clock timeout.")
    p.add_argument("--sleep-seconds", type=int, default=5)
    p.add_argument("--lease-seconds", type=int, default=0)
    p.add_argument("--no-auto-operator", action="store_true", help="Disable automatic add-repair-task / resolve-by-repair / recover-stale handling when no ready task exists.")
    p.add_argument("--operator-stale-minutes", type=float, default=30.0)
    p.add_argument("--max-auto-repair-depth", type=int, default=3)

    p = sub.add_parser("launch-tmux", help="Start a background tmux worker loop.")
    p.add_argument("--workspace", default=".")
    p.add_argument("--worker-id", required=True)
    p.add_argument("--max-cycles", type=int, default=0, help="0 means unlimited cycles; no NodeKit wall-clock timeout.")
    p.add_argument("--session-name")

    p = sub.add_parser("background-doctor", help="Detect available background worker backends for this OS: tmux/nohup/setsid/powershell/foreground.")
    p.add_argument("--workspace", default=".")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("launch-background", help="Launch an unlimited background worker with the best available backend for this OS.")
    p.add_argument("--workspace", default=".")
    p.add_argument("--worker-id", required=True)
    p.add_argument("--backend", choices=["tmux", "nohup", "setsid", "detached", "powershell", "foreground"], help="Override auto-detected backend.")
    p.add_argument("--max-cycles", type=int, default=0, help="0 means unlimited cycles; no NodeKit wall-clock timeout.")
    p.add_argument("--sleep-seconds", type=int, default=5)
    p.add_argument("--lease-seconds", type=int, default=0)
    p.add_argument("--session-name")
    p.add_argument("--no-auto-operator", action="store_true", help="Disable the background worker's built-in operator automation.")
    p.add_argument("--operator-stale-minutes", type=float, default=30.0)
    p.add_argument("--max-auto-repair-depth", type=int, default=3)

    p = sub.add_parser("operator-step", help="Run one supervisor/control-plane step: auto add repair, resolve passed repair, recover stale, or launch background if requested.")
    p.add_argument("--workspace", default=".")
    p.add_argument("--worker-id", default="codex-worker")
    p.add_argument("--stale-minutes", type=float, default=30.0)
    p.add_argument("--max-auto-repair-depth", type=int, default=3)
    p.add_argument("--start-background", action="store_true")
    p.add_argument("--backend", choices=["tmux", "nohup", "setsid", "detached", "powershell", "foreground"], help="Backend to use when --start-background is needed.")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("operator-loop", help="Run the supervisor loop. It handles routine repair/recover/resolve transitions; it does not approve human gates.")
    p.add_argument("--workspace", default=".")
    p.add_argument("--worker-id", default="codex-worker")
    p.add_argument("--max-cycles", type=int, default=0)
    p.add_argument("--sleep-seconds", type=int, default=10)
    p.add_argument("--stale-minutes", type=float, default=30.0)
    p.add_argument("--max-auto-repair-depth", type=int, default=3)
    p.add_argument("--start-background", action="store_true")
    p.add_argument("--backend", choices=["tmux", "nohup", "setsid", "detached", "powershell", "foreground"], help="Backend to use when --start-background is needed.")

    p = sub.add_parser("recover-stale", help="Inspect or mark stale running task runs for repair instead of leaving them stuck in running.")
    p.add_argument("--workspace", default=".")
    p.add_argument("--run-id")
    p.add_argument("--age-minutes", type=float, default=30.0)
    p.add_argument("--mark-failed", action="store_true", help="Write an inferred failed worker_result.json and finish the run with exit_code=1.")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("resolve-by-repair", help="Resolve a failed task by a passed repair task and rewire downstream gating edges to the repair evidence.")
    p.add_argument("--workspace", default=".")
    p.add_argument("--failed-task-id", required=True)
    p.add_argument("--repair-task-id", required=True)
    p.add_argument("--summary", default="Resolved by passed repair task.")

    p = sub.add_parser("background-status", help="Inspect background heartbeat/launch metadata for one worker.")
    p.add_argument("--workspace", default=".")
    p.add_argument("--worker-id", default="codex-worker")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("shell-safety-lint", help="Lint a shell command for verifier/bootstrap safety issues such as command substitution or mutating Slurm commands.")
    p.add_argument("--command", required=True)
    p.add_argument("--purpose", default="verifier", choices=["verifier", "bootstrap", "preflight", "doctor", "worker"])
    p.add_argument("--platform", default=None)
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("apply-graph-patch", help="Apply a graph_patch JSON file.")
    p.add_argument("--workspace", default=".")
    p.add_argument("--file", type=Path, required=True)

    p = sub.add_parser("start-figures", help="Strong one-command setup for a contract-gated Codex figure batch.")
    p.add_argument("--workspace", default=".")
    p.add_argument("--figures", type=int, required=True)
    p.add_argument("--journal", required=True)
    p.add_argument("--project-name", default="journal-figure-batch")
    p.add_argument("--output-dir", default="outputs/figures")
    p.add_argument("--tasks-per-figure", type=int, default=3, choices=[2, 3, 4])
    p.add_argument("--task-scale", choices=["smoke", "standard", "prod"], help="Optional scale alias: smoke=2, standard=3, prod=4 tasks per artifact.")
    p.add_argument("--gate-mode", default="strict", choices=["fast", "balanced", "strict"], help="Human gate policy. strict preserves separate setup/plan/pilot gates.")
    p.add_argument("--force-codex-native", action="store_true", help="Overwrite existing Codex-native files if needed.")

    p = sub.add_parser("spec-from-prompt", help="Draft PROJECT_SPEC.yml from a natural-language project prompt without starting the graph.")
    p.add_argument("--workspace", default=".")
    p.add_argument("--prompt-file", type=Path, required=True)
    p.add_argument("--figures", type=int, help="Override or supply artifact count when not parseable from prompt.")
    p.add_argument("--journal", help="Override or supply journal name.")
    p.add_argument("--project-name", help="Override project name.")
    p.add_argument("--output-dir", default="outputs/figures")
    p.add_argument("--data-dir", default="data")
    p.add_argument("--tasks-per-figure", type=int, default=3, choices=[2, 3, 4])
    p.add_argument("--task-scale", choices=["smoke", "standard", "prod"], help="Optional scale alias: smoke=2, standard=3, prod=4 tasks per artifact.")
    p.add_argument("--gate-mode", default="fast", choices=["fast", "balanced", "strict"], help="Default fast: one startup review, then loop. balanced adds pilot review; strict splits setup/plan/pilot gates.")

    p = sub.add_parser("start-from-prompt", help="One-command prompt-to-spec-to-manifest startup for a Codex-native figure loop.")
    p.add_argument("--workspace", default=".")
    p.add_argument("--prompt-file", type=Path, required=True)
    p.add_argument("--figures", type=int, help="Override or supply artifact count when not parseable from prompt.")
    p.add_argument("--journal", help="Override or supply journal name.")
    p.add_argument("--project-name", help="Override project name.")
    p.add_argument("--output-dir", default="outputs/figures")
    p.add_argument("--data-dir", default="data")
    p.add_argument("--tasks-per-figure", type=int, default=3, choices=[2, 3, 4])
    p.add_argument("--task-scale", choices=["smoke", "standard", "prod"], help="Optional scale alias: smoke=2, standard=3, prod=4 tasks per artifact.")
    p.add_argument("--gate-mode", default="fast", choices=["fast", "balanced", "strict"], help="Default fast minimizes human stops while keeping startup review, boundary test, verifier, Santa, repair, and final audit.")
    p.add_argument("--force-codex-native", action="store_true")

    p = sub.add_parser("smart-start", help="Fixed autopilot-nodekit startup: analyze prompt, ask missing settings, then generate spec/contract/manifest and start.")
    p.add_argument("--workspace", default=".")
    p.add_argument("--prompt-file", type=Path, default=Path("PROJECT_PROMPT.md"))
    p.add_argument("--answers", type=Path, default=Path("START_ANSWERS.yml"), help="Optional answers file produced from START_ANSWERS.yml.template.")
    p.add_argument("--figures", type=int, help="Override or supply artifact count.")
    p.add_argument("--journal", help="Override or supply target journal.")
    p.add_argument("--project-name", help="Override project name.")
    p.add_argument("--output-dir", help="Override output directory. Default is inferred or outputs/figures.")
    p.add_argument("--data-dir", help="Override data directory. Default is inferred or data.")
    p.add_argument("--gate-mode", choices=["fast", "balanced", "strict"], help="Required if prompt does not specify it; no silent default.")
    p.add_argument("--task-scale", choices=["smoke", "standard", "prod"], help="Required if prompt does not specify it; maps to 2/3/4 tasks per artifact.")
    p.add_argument("--force-codex-native", action="store_true")

    p = sub.add_parser("start-from-spec", help="Start a Codex-native figure loop from PROJECT_SPEC.yml.")
    p.add_argument("--workspace", default=".")
    p.add_argument("--spec", type=Path, default=Path("PROJECT_SPEC.yml"))
    p.add_argument("--force-codex-native", action="store_true")

    p = sub.add_parser("project-spec-review", help="Print PROJECT_SPEC.md review file.")
    p.add_argument("--workspace", default=".")

    p = sub.add_parser("codex-spec-goal", help="Print a native Codex /goal to draft PROJECT_SPEC.yml from PROJECT_PROMPT.md.")
    p.add_argument("--workspace", default=".")
    p.add_argument("--prompt-file", type=Path, default=Path("PROJECT_PROMPT.md"))
    p.add_argument("--output", type=Path)

    p = sub.add_parser("codex-draft-spec", help="Prepare or run a Codex exec handoff that drafts PROJECT_SPEC.yml from PROJECT_PROMPT.md.")
    p.add_argument("--workspace", default=".")
    p.add_argument("--prompt-file", type=Path, default=Path("PROJECT_PROMPT.md"))
    p.add_argument("--gate-mode", default="fast", choices=["fast", "balanced", "strict"], help="Gate mode the AI spec drafter should encode unless prompt overrides it.")
    p.add_argument("--run", action="store_true", help="Immediately run the generated Codex exec script. Requires authenticated Codex CLI.")

    p = sub.add_parser("approve-start", help="Approve the combined startup gate G000_START_REVIEW for fast/balanced workflows.")
    p.add_argument("--workspace", default=".")
    p.add_argument("--summary", default="Project spec, Layer 0 setup, contract, task manifest, permissions, and loop mode reviewed.")

    p = sub.add_parser("setup-review", help="Render and print the Layer 0 setup review file.")
    p.add_argument("--workspace", default=".")

    p = sub.add_parser("contract-review", help="Render and print the goal contract review file.")
    p.add_argument("--workspace", default=".")

    p = sub.add_parser("contract-validate", help="Validate GOAL_CONTRACT.yml and automation/manifest.yml together.")
    p.add_argument("--workspace", default=".")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("codex-contract-goal", help="Print a native Codex /goal for the whole contract-gated project.")
    p.add_argument("--workspace", default=".")
    p.add_argument("--output", type=Path)

    p = sub.add_parser("next-command", help="Print exactly one strong next command for the current workflow state.")
    p.add_argument("--workspace", default=".")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("generate-figure-plan", help="Generate a review-gated journal-figure task graph with 2-4 tasks per figure.")
    p.add_argument("--workspace", default=".")
    p.add_argument("--figures", type=int, required=True, help="Number of figures/artifacts to produce.")
    p.add_argument("--journal", default="target journal")
    p.add_argument("--project-name", default="journal-figure-batch")
    p.add_argument("--output-dir", default="outputs/figures")
    p.add_argument("--tasks-per-figure", type=int, default=3, choices=[2, 3, 4])
    p.add_argument("--task-scale", choices=["smoke", "standard", "prod"], help="Optional scale alias: smoke=2, standard=3, prod=4 tasks per artifact.")
    p.add_argument("--gate-mode", default="strict", choices=["fast", "balanced", "strict"], help="Human gate policy. fast minimizes stops; balanced adds pilot review; strict uses separate setup/plan/pilot gates.")
    p.add_argument("--no-import", action="store_true", help="Only write automation/manifest.yml and review files; do not import into SQLite.")
    p.add_argument("--append", action="store_true", help="Append/upsert into existing graph instead of resetting tasks/runs/memory first.")

    p = sub.add_parser("review-plan", help="Render TASK_REVIEW.md and REQUIREMENTS_LOCK.md from automation/manifest.yml.")
    p.add_argument("--workspace", default=".")

    p = sub.add_parser("approve-task", help="Manually approve a review gate task and record an audit event.")
    p.add_argument("--workspace", default=".")
    p.add_argument("--task-id", required=True)
    p.add_argument("--summary", default="Human approved.")
    p.add_argument("--force", action="store_true", help="Allow approval even if prerequisite gates are not satisfied.")

    p = sub.add_parser("reject-task", help="Manually reject/block a review gate task and record an audit event.")
    p.add_argument("--workspace", default=".")
    p.add_argument("--task-id", required=True)
    p.add_argument("--summary", default="Human rejected; blocked for revision.")

    p = sub.add_parser("approve-setup", help="Approve the Layer 0 setup gate G000_SETUP_REVIEW.")
    p.add_argument("--workspace", default=".")
    p.add_argument("--summary", default="Layer 0 setup reviewed and approved.")

    p = sub.add_parser("approve-plan", help="Approve the generated plan review gate H000_PLAN_REVIEW.")
    p.add_argument("--workspace", default=".")
    p.add_argument("--summary", default="Plan reviewed and approved.")

    p = sub.add_parser("approve-pilot", help="Approve the first artifact pilot review gate H020_PILOT_REVIEW.")
    p.add_argument("--workspace", default=".")
    p.add_argument("--summary", default="Pilot artifact reviewed and approved for batch loop.")
    p.add_argument("--force", action="store_true")

    p = sub.add_parser("verify-artifact", help="Verify that an output artifact exists inside the workspace and is non-empty.")
    p.add_argument("--workspace", default=".")
    p.add_argument("--glob", required=True, help="Glob relative to workspace, e.g. outputs/figures/F001*.")
    p.add_argument("--min-bytes", type=int, default=1)
    p.add_argument("--suffix", action="append", default=[], help="Allowed suffix, repeatable, e.g. --suffix .pdf --suffix .png")

    p = sub.add_parser("codex-prepare", help="Claim one ready task and prepare a fresh interactive Codex conversation for it.")
    p.add_argument("--workspace", default=".")
    p.add_argument("--worker-id", default="codex-interactive")
    p.add_argument("--lease-seconds", type=int, default=7200)

    p = sub.add_parser("codex-finish", help="Finish a prepared interactive Codex run after worker_result.json exists.")
    p.add_argument("--workspace", default=".")
    p.add_argument("--run-id", required=True)
    p.add_argument("--exit-code", type=int)

    p = sub.add_parser("memory-search", help="Search structured memory nodes with SQLite FTS.")
    p.add_argument("--workspace", default=".")
    p.add_argument("query", nargs="?", default="")
    p.add_argument("--limit", type=int, default=10)

    p = sub.add_parser("memory-plan", help="Preview the exact memory nodes that would be injected for a task without claiming/running it.")
    p.add_argument("--workspace", default=".")
    p.add_argument("--task-id", required=True)
    p.add_argument("--json", action="store_true", help="Print full retrieval result as JSON.")

    p = sub.add_parser("memory-for-task", help="Alias for memory-plan.")
    p.add_argument("--workspace", default=".")
    p.add_argument("--task-id", required=True)
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("codex-goal", help="Print a native Codex /goal command for a NodeKit task.")
    p.add_argument("--workspace", default=".")
    p.add_argument("--task-id", help="Task id to target. Defaults to the highest-priority ready task.")
    p.add_argument("--worker-id", default="codex-goal", help="Worker id mentioned in the generated run-once command.")
    p.add_argument("--output", type=Path, help="Write a Markdown goal handoff file as well as printing the goal.")
    p.add_argument("--json", action="store_true", help="Print metadata and goal as JSON.")

    p = sub.add_parser("metrics", help="Write and print observability metrics for the current run graph.")
    p.add_argument("--workspace", default=".")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("replay-run", help="Print replay/audit file paths for a run id.")
    p.add_argument("--workspace", default=".")
    p.add_argument("--run-id", required=True)

    p = sub.add_parser("add-repair-task", help="Insert a focused repair task after a failed/blocked task.")
    p.add_argument("--workspace", default=".")
    p.add_argument("--failed-task-id", required=True)
    p.add_argument("--summary", required=True)
    p.add_argument("--priority", type=int)

    p = sub.add_parser("review-task", help="Print one task, its contract, gate edges, and latest runs as JSON.")
    p.add_argument("--workspace", default=".")
    p.add_argument("--task-id", required=True)

    p = sub.add_parser("doctor", help="Check local tools for Codex-native usage.")
    p.add_argument("--workspace", default=".")

    args = parser.parse_args(argv)
    if args.cmd == "shell-safety-lint":
        findings = lint_shell_command(args.command, purpose=args.purpose, platform=args.platform)
        if args.json:
            print(json.dumps([f.to_dict() for f in findings], ensure_ascii=False, indent=2))
        else:
            print(render_findings(findings))
        return 2 if should_block(findings) else 0

    workspace = Path(args.workspace).resolve()
    paths = workspace_paths(workspace)

    if args.cmd == "doctor":
        return doctor(workspace)
    if args.cmd == "operator-step":
        db = AutoDB(paths["db"])
        db.init_schema()
        try:
            report = operator_step(
                workspace,
                db,
                worker_id=args.worker_id,
                stale_minutes=args.stale_minutes,
                max_auto_repair_depth=args.max_auto_repair_depth,
                start_background=args.start_background,
                backend=args.backend,
            )
            if args.json:
                print(json.dumps(report, ensure_ascii=False, indent=2))
            else:
                print(json.dumps(report, ensure_ascii=False, indent=2))
        finally:
            db.close()
        return 0
    if args.cmd == "operator-loop":
        db = AutoDB(paths["db"])
        db.init_schema()
        try:
            cycles = operator_loop(
                workspace,
                db,
                worker_id=args.worker_id,
                max_cycles=args.max_cycles,
                sleep_seconds=args.sleep_seconds,
                stale_minutes=args.stale_minutes,
                max_auto_repair_depth=args.max_auto_repair_depth,
                start_background=args.start_background,
                backend=args.backend,
            )
            print(f"operator-loop cycles={cycles}")
        finally:
            db.close()
        return 0
    if args.cmd == "background-doctor":
        info = detect_background_backends(workspace)
        if args.json:
            print(json.dumps(info, ensure_ascii=False, indent=2))
        else:
            rows = [(b["name"], "available" if b["available"] else "missing", b["detail"]) for b in info["backends"]]
            print(render_table(rows, ["backend", "status", "detail"]))
            print(f"\nSelected backend: {info['selected']}")
            print("No NodeKit wall-clock timeout is applied; use --max-cycles 0 for unlimited cycles.")
        return 0

    db = AutoDB(paths["db"])
    try:
        db.init_schema()
        if args.cmd == "init":
            install_initial_files(workspace, args.manifest, args.config, force=args.force)
            install_nodekit_runtime(workspace, force=args.force)
            ensure_memory_dirs(workspace)
            if args.codex_native:
                install_codex_native_files(workspace, force=args.force)
            import_manifest(db, paths["manifest"])
            render_live_manifest(workspace, db)
            print(f"Initialized autopilot-nodekit in {workspace}")
            print(f"Live manifest: {paths['live_md']}")
            if args.codex_native:
                print("Codex-native files installed.")
            return 0
        if args.cmd == "install-codex-native":
            install_codex_native_files(workspace, force=args.force)
            install_nodekit_runtime(workspace, force=args.force)
            print("Codex-native files and NodeKit runtime wrappers installed.")
            return 0
        if args.cmd == "import-manifest":
            import_manifest(db, args.manifest or paths["manifest"])
            render_live_manifest(workspace, db)
            print("Imported manifest and rendered live files.")
            return 0
        if args.cmd == "status":
            db.refresh_ready_tasks()
            render_live_manifest(workspace, db)
            rows = [(t["id"], t["status"], t["attempt_count"], t["title"], (t["result_summary"] or "")[:80]) for t in db.list_tasks()]
            print(render_table(rows, ["id", "status", "attempts", "title", "last_result"]))
            print(f"\nLive: {paths['live_md']}")
            return 0
        if args.cmd == "render":
            db.refresh_ready_tasks()
            render_live_manifest(workspace, db)
            print(f"Rendered {paths['live_md']} and {paths['live_tsv']}")
            return 0
        if args.cmd == "validate":
            report = validate_graph(db, workspace, strict=args.strict)
            if args.json:
                print(json.dumps(report, ensure_ascii=False, indent=2))
            else:
                print_validation_report(report)
            return 1 if report["errors"] else 0
        if args.cmd == "claim":
            claim = db.claim_ready_task(args.worker_id, args.lease_seconds)
            if not claim:
                print("No ready task.")
                return 0
            task, run_id = claim
            print(json.dumps({"task_id": task["id"], "run_id": run_id}, ensure_ascii=False, indent=2))
            return 0
        if args.cmd == "run-once":
            run_id = run_once(workspace, db, args.worker_id, lease_seconds=args.lease_seconds)
            print(f"run_id={run_id}" if run_id else "No ready task.")
            return 0
        if args.cmd == "worker-loop":
            cycles = worker_loop(
                workspace,
                db,
                args.worker_id,
                max_cycles=args.max_cycles,
                sleep_seconds=args.sleep_seconds,
                lease_seconds=args.lease_seconds,
                auto_operator=not args.no_auto_operator,
                operator_stale_minutes=args.operator_stale_minutes,
                max_auto_repair_depth=args.max_auto_repair_depth,
            )
            print(f"worker_loop cycles={cycles}")
            return 0
        if args.cmd == "launch-tmux":
            session = launch_tmux_worker(workspace, args.worker_id, args.max_cycles, args.session_name)
            print(f"Launched tmux session: {session}")
            print(f"Attach: tmux attach -t {session}")
            return 0
        if args.cmd == "launch-background":
            info = launch_background_worker(
                workspace,
                worker_id=args.worker_id,
                max_cycles=args.max_cycles,
                sleep_seconds=args.sleep_seconds,
                lease_seconds=args.lease_seconds,
                backend=args.backend,
                session_name=args.session_name,
                auto_operator=not args.no_auto_operator,
                operator_stale_minutes=args.operator_stale_minutes,
                max_auto_repair_depth=args.max_auto_repair_depth,
            )
            print(json.dumps(info, ensure_ascii=False, indent=2))
            return 0
        if args.cmd == "recover-stale":
            from .recovery import recover_stale_runs
            report = recover_stale_runs(workspace, db, run_id=args.run_id, age_minutes=args.age_minutes, mark_failed=args.mark_failed)
            render_live_manifest(workspace, db)
            if args.json:
                print(json.dumps(report, ensure_ascii=False, indent=2))
            else:
                print(render_table([(r.get("run_id"), r.get("task_id"), r.get("action"), r.get("reason")) for r in report["runs"]], ["run_id", "task_id", "action", "reason"]))
            return 0 if not report.get("errors") else 1
        if args.cmd == "resolve-by-repair":
            from .recovery import resolve_by_repair
            report = resolve_by_repair(db, args.failed_task_id, args.repair_task_id, summary=args.summary)
            render_live_manifest(workspace, db)
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 0
        if args.cmd == "background-status":
            from .background import background_status
            report = background_status(workspace, args.worker_id)
            if args.json:
                print(json.dumps(report, ensure_ascii=False, indent=2))
            else:
                print(json.dumps(report, ensure_ascii=False, indent=2))
            return 0
        if args.cmd == "start-figures":
            install_codex_native_files(workspace, force=args.force_codex_native)
            manifest = generate_journal_figure_manifest(
                figure_count=args.figures,
                project_name=args.project_name,
                journal=args.journal,
                output_dir=args.output_dir,
                tasks_per_figure=TASK_SCALE_TO_TASKS_PER_FIGURE[normalize_task_scale(args.task_scale)] if getattr(args, "task_scale", None) else args.tasks_per_figure,
                gate_mode=args.gate_mode,
            )
            write_figure_manifest(workspace, manifest)
            ensure_default_config(paths)
            db.reset_graph(keep_memory=False)
            import_manifest(db, paths["manifest"])
            render_live_manifest(workspace, db)
            report = validate_graph(db, workspace, strict=True)
            print(f"Started contract-gated Codex figure batch: figures={args.figures}, tasks={len(manifest['tasks'])}")
            print(f"Review layer 0 first: {workspace / 'SETUP_REVIEW.md'}")
            print(f"Review contract: {workspace / 'GOAL_CONTRACT.md'}")
            print(f"Review task plan: {workspace / 'TASK_REVIEW.md'}")
            print(format_next_command(compute_next_command(workspace, db)))
            return 1 if report["errors"] else 0
        if args.cmd == "spec-from-prompt":
            prompt_path = args.prompt_file if args.prompt_file.is_absolute() else workspace / args.prompt_file
            prompt_text = prompt_path.read_text(encoding="utf-8")
            tasks_per_figure = TASK_SCALE_TO_TASKS_PER_FIGURE[normalize_task_scale(args.task_scale)] if getattr(args, "task_scale", None) else args.tasks_per_figure
            spec = infer_project_spec_from_prompt(
                prompt_text,
                figures=args.figures,
                journal=args.journal,
                project_name=args.project_name,
                output_dir=args.output_dir,
                data_dir=args.data_dir,
                tasks_per_figure=tasks_per_figure,
                gate_mode=args.gate_mode,
            )
            write_project_spec(workspace, spec, prompt_text=prompt_text)
            print(f"Wrote {workspace / 'PROJECT_SPEC.yml'}")
            print(f"Wrote {workspace / 'PROJECT_SPEC.md'}")
            print("Next: python -m autopilot_nodekit start-from-spec --workspace . --spec PROJECT_SPEC.yml --force-codex-native")
            return 0
        if args.cmd == "start-from-prompt":
            install_codex_native_files(workspace, force=args.force_codex_native)
            prompt_path = args.prompt_file if args.prompt_file.is_absolute() else workspace / args.prompt_file
            prompt_text = prompt_path.read_text(encoding="utf-8")
            tasks_per_figure = TASK_SCALE_TO_TASKS_PER_FIGURE[normalize_task_scale(args.task_scale)] if getattr(args, "task_scale", None) else args.tasks_per_figure
            spec = infer_project_spec_from_prompt(
                prompt_text,
                figures=args.figures,
                journal=args.journal,
                project_name=args.project_name,
                output_dir=args.output_dir,
                data_dir=args.data_dir,
                tasks_per_figure=tasks_per_figure,
                gate_mode=args.gate_mode,
            )
            write_project_spec(workspace, spec, prompt_text=prompt_text)
            manifest = manifest_from_project_spec(spec)
            write_manifest_for_project(workspace, manifest, spec)
            ensure_default_config(paths)
            db.reset_graph(keep_memory=False)
            import_manifest(db, paths["manifest"])
            render_live_manifest(workspace, db)
            report = validate_graph(db, workspace, strict=True)
            project = manifest.get("project", {}) or {}
            print(f"Started prompt-derived Codex loop: artifacts={project.get('artifact_count')}, tasks={len(manifest['tasks'])}, gate_mode={project.get('gate_mode')}")
            print(f"Review spec: {workspace / 'PROJECT_SPEC.md'}")
            print(f"Review task plan: {workspace / 'TASK_REVIEW.md'}")
            print(format_next_command(compute_next_command(workspace, db)))
            return 1 if report["errors"] else 0
        if args.cmd == "smart-start":
            install_codex_native_files(workspace, force=args.force_codex_native)
            prompt_path = args.prompt_file if args.prompt_file.is_absolute() else workspace / args.prompt_file
            if not prompt_path.exists():
                print(f"Missing prompt file: {prompt_path}")
                return 1
            prompt_text = prompt_path.read_text(encoding="utf-8")
            answers_path = args.answers if args.answers.is_absolute() else workspace / args.answers
            answers = load_start_answers(answers_path if answers_path.exists() else None)
            analysis = analyze_start_prompt(
                prompt_text,
                figures=args.figures,
                journal=args.journal,
                gate_mode=args.gate_mode,
                task_scale=args.task_scale,
                project_name=args.project_name,
                output_dir=args.output_dir,
                data_dir=args.data_dir,
                answers=answers,
            )
            if answers_path.exists() and not bool(answers.get("confirmed")):
                analysis.missing.append({"field": "confirmed", "question": "START_ANSWERS.yml exists but confirmed is not true. Set confirmed: true after reviewing answers.", "default": True})
            if not analysis.ready:
                write_start_questions(workspace, analysis)
                print("Startup is blocked for required settings. Wrote START_QUESTIONS.md and START_ANSWERS.yml.template.")
                print(workspace / "START_QUESTIONS.md")
                print("Next: copy START_ANSWERS.yml.template to START_ANSWERS.yml, fill it, set confirmed: true, then rerun smart-start.")
                return 2
            spec = build_spec_from_resolved(prompt_text, analysis.resolved)
            write_project_spec(workspace, spec, prompt_text=prompt_text)
            manifest = manifest_from_project_spec(spec)
            write_manifest_for_project(workspace, manifest, spec)
            ensure_default_config(paths)
            db.reset_graph(keep_memory=False)
            import_manifest(db, paths["manifest"])
            render_live_manifest(workspace, db)
            report = validate_graph(db, workspace, strict=True)
            project = manifest.get("project", {}) or {}
            print(f"Smart-started Codex loop: artifacts={project.get('artifact_count')}, tasks={len(manifest['tasks'])}, gate_mode={project.get('gate_mode')}, task_scale={project.get('task_scale')}")
            print(f"Review spec: {workspace / 'PROJECT_SPEC.md'}")
            print(f"Review task plan: {workspace / 'TASK_REVIEW.md'}")
            print(format_next_command(compute_next_command(workspace, db)))
            return 1 if report["errors"] else 0
        if args.cmd == "start-from-spec":
            install_codex_native_files(workspace, force=args.force_codex_native)
            spec_path = args.spec if args.spec.is_absolute() else workspace / args.spec
            spec = load_yaml(spec_path)
            write_project_spec(workspace, spec)
            manifest = manifest_from_project_spec(spec)
            write_manifest_for_project(workspace, manifest, spec)
            ensure_default_config(paths)
            db.reset_graph(keep_memory=False)
            import_manifest(db, paths["manifest"])
            render_live_manifest(workspace, db)
            report = validate_graph(db, workspace, strict=True)
            project = manifest.get("project", {}) or {}
            print(f"Started Codex loop from spec: artifacts={project.get('artifact_count')}, tasks={len(manifest['tasks'])}, gate_mode={project.get('gate_mode')}")
            print(format_next_command(compute_next_command(workspace, db)))
            return 1 if report["errors"] else 0
        if args.cmd == "project-spec-review":
            spec = load_project_spec(workspace)
            if not spec:
                print("Missing PROJECT_SPEC.yml")
                return 1
            from .project_spec import render_project_spec_review
            text = render_project_spec_review(spec)
            from .util import write_text
            write_text(workspace / "PROJECT_SPEC.md", text)
            print(text)
            return 0
        if args.cmd == "codex-spec-goal":
            goal = build_codex_spec_goal(args.prompt_file, "PROJECT_SPEC.yml")
            if args.output:
                from .util import write_text
                out = args.output if args.output.is_absolute() else workspace / args.output
                write_text(out, "# Codex Project Spec Goal\n\n```text\n" + goal + "\n```\n")
                print(f"Wrote {out}")
            print(goal)
            return 0
        if args.cmd == "codex-draft-spec":
            prompt_path = args.prompt_file if args.prompt_file.is_absolute() else workspace / args.prompt_file
            info = prepare_codex_spec_draft(workspace, prompt_path, gate_mode=args.gate_mode)
            print(json.dumps(info, ensure_ascii=False, indent=2))
            print(f"Run: {info['command']}")
            if args.run:
                completed = subprocess.run(["bash", info["script"]], cwd=str(workspace))
                return int(completed.returncode)
            return 0
        if args.cmd == "approve-start":
            db.approve_task("G000_START_REVIEW", summary=args.summary, require_gates=True)
            render_live_manifest(workspace, db)
            print("Approved G000_START_REVIEW. Run background-doctor, then launch-background to let the worker/operator continue. Use next-command only for diagnosis.")
            return 0
        if args.cmd == "setup-review":
            setup = load_project_setup(workspace)
            if not setup:
                print("Missing PROJECT_SETUP.yml")
                return 1
            text = render_setup_review(setup)
            from .util import write_text
            write_text(workspace / "SETUP_REVIEW.md", text)
            print(text)
            return 0
        if args.cmd == "contract-review":
            contract = load_goal_contract(workspace)
            if not contract:
                print("Missing GOAL_CONTRACT.yml")
                return 1
            text = render_goal_contract_review(contract)
            from .util import write_text
            write_text(workspace / "GOAL_CONTRACT.md", text)
            print(text)
            return 0
        if args.cmd == "contract-validate":
            contract = load_goal_contract(workspace)
            try:
                manifest = load_yaml(paths["manifest"])
            except Exception:
                manifest = None
            report = validate_goal_contract(contract, manifest=manifest)
            if args.json:
                print(json.dumps(report, ensure_ascii=False, indent=2))
            else:
                print_validation_report(report)
            return 1 if report["errors"] else 0
        if args.cmd == "codex-contract-goal":
            contract = load_goal_contract(workspace)
            if not contract:
                print("Missing GOAL_CONTRACT.yml")
                return 1
            goal = build_contract_goal_text(contract)
            if args.output:
                from .util import write_text
                out = args.output if args.output.is_absolute() else workspace / args.output
                write_text(out, "# Codex Contract Goal\n\n```text\n" + goal + "\n```\n")
                print(f"Wrote {out}")
            print(goal)
            return 0
        if args.cmd == "next-command":
            info = compute_next_command(workspace, db)
            if args.json:
                print(json.dumps(info, ensure_ascii=False, indent=2))
            else:
                print(format_next_command(info))
            return 0
        if args.cmd == "generate-figure-plan":
            manifest = generate_journal_figure_manifest(
                figure_count=args.figures,
                project_name=args.project_name,
                journal=args.journal,
                output_dir=args.output_dir,
                tasks_per_figure=TASK_SCALE_TO_TASKS_PER_FIGURE[normalize_task_scale(args.task_scale)] if getattr(args, "task_scale", None) else args.tasks_per_figure,
                gate_mode=args.gate_mode,
            )
            write_figure_manifest(workspace, manifest)
            ensure_default_config(paths)
            if not args.no_import:
                if not args.append:
                    db.reset_graph(keep_memory=False)
                import_manifest(db, paths["manifest"])
                render_live_manifest(workspace, db)
            print(f"Generated review-gated figure plan: figures={args.figures}, tasks={len(manifest['tasks'])}")
            print(f"Review layer 0 first: {workspace / 'SETUP_REVIEW.md'}")
            print(f"Review contract: {workspace / 'GOAL_CONTRACT.md'}")
            print(f"Review task plan: {workspace / 'TASK_REVIEW.md'}")
            print(format_next_command(compute_next_command(workspace, db)))
            return 0
        if args.cmd == "review-plan":
            from .util import load_yaml
            manifest = load_yaml(paths["manifest"])
            write_review_files(workspace, manifest)
            render_live_manifest(workspace, db)
            print(f"Wrote {workspace / 'TASK_REVIEW.md'} and {workspace / 'REQUIREMENTS_LOCK.md'}")
            return 0
        if args.cmd == "approve-task":
            db.approve_task(args.task_id, summary=args.summary, require_gates=not args.force)
            render_live_manifest(workspace, db)
            print(f"Approved {args.task_id}")
            return 0
        if args.cmd == "reject-task":
            db.reject_task(args.task_id, summary=args.summary)
            render_live_manifest(workspace, db)
            print(f"Rejected/blocked {args.task_id}")
            return 0
        if args.cmd == "approve-setup":
            db.approve_task("G000_SETUP_REVIEW", summary=args.summary, require_gates=True)
            render_live_manifest(workspace, db)
            print("Approved G000_SETUP_REVIEW. Plan review can now be approved after human inspection.")
            return 0
        if args.cmd == "approve-plan":
            db.approve_task("H000_PLAN_REVIEW", summary=args.summary, require_gates=True)
            render_live_manifest(workspace, db)
            print("Approved H000_PLAN_REVIEW. Boundary/permission test can now release.")
            return 0
        if args.cmd == "approve-pilot":
            db.approve_task("H020_PILOT_REVIEW", summary=args.summary, require_gates=not args.force)
            render_live_manifest(workspace, db)
            print("Approved H020_PILOT_REVIEW. Bulk loop can now release.")
            return 0
        if args.cmd == "verify-artifact":
            ok, message = verify_artifact(workspace, args.glob, min_bytes=args.min_bytes, allowed_suffixes=args.suffix)
            print(message)
            return 0 if ok else 1
        if args.cmd == "codex-prepare":
            run_id = prepare_interactive_codex_run(workspace, db, args.worker_id, lease_seconds=args.lease_seconds)
            if not run_id:
                print("No ready task.")
                return 0
            open_script = workspace / "runs" / run_id / "open_codex.sh"
            print(f"run_id={run_id}")
            print(f"Open Codex task dialog: bash {open_script}")
            print(f"Finish after worker_result.json exists: python -m autopilot_nodekit codex-finish --workspace . --run-id {run_id}")
            return 0
        if args.cmd == "codex-finish":
            status = finish_prepared_codex_run(workspace, db, args.run_id, exit_code=args.exit_code)
            print(f"finished {args.run_id}: status={status}")
            return 0 if status in {"passed", "skipped"} else 1
        if args.cmd == "apply-graph-patch":
            patch = load_patch(args.file)
            count = apply_graph_patch(db, patch, source=str(args.file))
            render_live_manifest(workspace, db)
            print(f"Applied {count} graph operations.")
            return 0
        if args.cmd == "codex-goal":
            result = build_codex_goal(workspace, db, task_id=args.task_id, worker_id=args.worker_id)
            if args.output:
                write_codex_goal_file(args.output if args.output.is_absolute() else workspace / args.output, result)
            if args.json:
                print(json.dumps(result, ensure_ascii=False, indent=2))
            else:
                print(result["goal"])
                if args.output:
                    print(f"\nWrote: {args.output if args.output.is_absolute() else workspace / args.output}")
            return 0
        if args.cmd == "metrics":
            metrics = write_metrics_report(workspace, db)
            if args.json:
                print(json.dumps(metrics, ensure_ascii=False, indent=2))
            else:
                print(f"Wrote {paths['automation'] / 'metrics.json'}")
                print(f"Wrote {paths['automation'] / 'metrics.md'}")
                print(json.dumps(metrics, ensure_ascii=False, indent=2))
            return 0
        if args.cmd == "replay-run":
            run = db.get_run(args.run_id)
            if run is None:
                print(f"Run not found: {args.run_id}")
                return 1
            data = {k: run[k] for k in run.keys()}
            run_dir = paths["runs"] / args.run_id
            data["run_dir"] = str(run_dir)
            data["standard_files"] = [str(run_dir / name) for name in ["prompt.md", "context_pack.json", "memory_selection.json", "stdout.log", "stderr.log", "worker_result.json", "worker_result.normalized.json", "control_result.json"]]
            print(json.dumps(data, ensure_ascii=False, indent=2))
            return 0
        if args.cmd == "add-repair-task":
            repair_id = add_repair_task(db, args.failed_task_id, args.summary, priority=args.priority)
            render_live_manifest(workspace, db)
            print(f"Added repair task: {repair_id}")
            print(f"Next: python -m autopilot_nodekit codex-prepare --workspace . --worker-id codex-interactive")
            return 0
        if args.cmd == "review-task":
            task = db.get_task(args.task_id)
            if task is None:
                print(f"Task not found: {args.task_id}")
                return 1
            payload = {"task": {k: task[k] for k in task.keys()}, "edges": [dict(e) for e in db.list_edges(from_task=args.task_id)], "runs": [dict(r) for r in db.list_runs(args.task_id)[:10]]}
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 0
        if args.cmd == "memory-search":
            rows = db.search_memory(args.query, args.limit)
            print(render_table([(m["id"], m["scope"], m["title"], m["node_dir"]) for m in rows], ["id", "scope", "title", "node_dir"]))
            return 0
        if args.cmd in {"memory-plan", "memory-for-task"}:
            result = collect_memory_for_task(workspace, db, args.task_id)
            if args.json:
                print(json.dumps(result, ensure_ascii=False, indent=2))
            else:
                rows = []
                for m in result["nodes"]:
                    rows.append((m["id"], m.get("task_id"), m["scope"], "; ".join(m.get("retrieval_reasons", []))[:100], m["title"]))
                print(render_table(rows, ["memory_id", "source_task", "scope", "retrieval_reasons", "title"]))
                retrieval = result["retrieval"]
                print(f"\nloaded_count={retrieval.get('loaded_count')} omitted_due_to_limit={retrieval.get('omitted_due_to_limit')}")
                if retrieval.get("unresolved_requirements"):
                    print("unresolved_requirements:")
                    for item in retrieval["unresolved_requirements"]:
                        print(f"- {item}")
            return 0
    finally:
        db.close()
    return 1


def validate_graph(db: AutoDB, workspace: Path | None = None, strict: bool = False) -> dict[str, list[dict[str, Any]]]:
    tasks = {t["id"]: t for t in db.list_tasks()}
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    edges = db.list_edges()

    for edge in edges:
        if edge["from_task"] not in tasks:
            errors.append({"type": "dangling_from_task", "from_task": edge["from_task"], "to_task": edge["to_task"], "edge_type": edge["edge_type"]})
        if edge["to_task"] not in tasks:
            errors.append({"type": "dangling_to_task", "from_task": edge["from_task"], "to_task": edge["to_task"], "edge_type": edge["edge_type"]})

    for cycle in find_cycles(edges, tasks):
        errors.append({"type": "gating_cycle", "cycle": cycle})

    for task in tasks.values():
        task_id = task["id"]
        if task["status"] in {"planned", "blocked"} and db.has_gating_edges(task_id) and db.gates_satisfied(task_id):
            warnings.append({"type": "ready_on_refresh", "task_id": task_id, "status": task["status"]})
        if task["status"] == "blocked" and not db.has_gating_edges(task_id):
            warnings.append({"type": "human_or_patch_blocked", "task_id": task_id})
        try:
            memory = json.loads(task["memory_policy_json"] or "{}")
        except Exception:
            errors.append({"type": "invalid_memory_policy_json", "task_id": task_id})
            memory = {}
        for rid in memory.get("required_task_ids", []) or []:
            if str(rid) not in tasks:
                warnings.append({"type": "missing_required_task_id", "task_id": task_id, "required_task_id": rid})
        try:
            json.loads(task["verifier_json"] or "{}")
        except Exception:
            errors.append({"type": "invalid_verifier_json", "task_id": task_id})
        try:
            task_contract = json.loads(task["task_contract_json"] or "{}")
        except Exception:
            errors.append({"type": "invalid_task_contract_json", "task_id": task_id})
            task_contract = {}
        if strict:
            for field in ["input_files", "expected_outputs", "done_when"]:
                if not task_contract.get(field):
                    errors.append({"type": "task_missing_verifiable_contract_field", "task_id": task_id, "field": field})
            if not bool(task_contract.get("human_review_required")):
                policy = task_contract.get("review_policy") or {}
                if not isinstance(policy, dict) or policy.get("method") != "santa_dual_review" or policy.get("required") is not True:
                    errors.append({"type": "task_missing_required_santa_review_policy", "task_id": task_id})

    if workspace is not None:
        add_plan_quality_checks(workspace, tasks, edges, errors, warnings, strict=strict)

    return {"errors": errors, "warnings": warnings}


def add_plan_quality_checks(workspace: Path, tasks: dict[str, Any], edges: list[Any], errors: list[dict[str, Any]], warnings: list[dict[str, Any]], strict: bool = False) -> None:
    manifest_path = workspace_paths(workspace)["manifest"]
    try:
        manifest = load_yaml(manifest_path)
    except Exception:
        return
    project = manifest.get("project", {}) or {}
    if not isinstance(project, dict) or project.get("plan_type") != "journal_figures":
        return

    gate_mode = str(project.get("gate_mode") or "strict").strip().lower()
    if gate_mode not in {"fast", "balanced", "strict"}:
        errors.append({"type": "invalid_gate_mode", "gate_mode": gate_mode})
        gate_mode = "strict"

    if strict or project.get("setup_required"):
        setup_report = validate_project_setup(workspace)
        errors.extend(setup_report.get("errors", []))
        warnings.extend(setup_report.get("warnings", []))
    if strict or project.get("goal_contract_required"):
        contract_report = validate_goal_contract(load_goal_contract(workspace), manifest=manifest)
        errors.extend(contract_report.get("errors", []))
        warnings.extend(contract_report.get("warnings", []))

    expected = int(project.get("artifact_count") or 0)
    minimum = int(project.get("minimum_task_count") or max(expected, expected * 2))
    if len(tasks) < minimum:
        errors.append({"type": "too_few_tasks_for_artifacts", "artifact_count": expected, "minimum_task_count": minimum, "actual_task_count": len(tasks)})

    gates = dict(project.get("review_gates") or {})
    if gate_mode == "fast":
        required = {"start": gates.get("start", "G000_START_REVIEW"), "boundary_test": gates.get("boundary_test", "H010_BOUNDARY_PERMISSION_TEST"), "final_audit": gates.get("final_audit", "Z999_FINAL_AUDIT")}
    elif gate_mode == "balanced":
        required = {"start": gates.get("start", "G000_START_REVIEW"), "boundary_test": gates.get("boundary_test", "H010_BOUNDARY_PERMISSION_TEST"), "pilot": gates.get("pilot", "H020_PILOT_REVIEW"), "final_audit": gates.get("final_audit", "Z999_FINAL_AUDIT")}
    else:
        required = {"setup": gates.get("setup", "G000_SETUP_REVIEW"), "plan": gates.get("plan", "H000_PLAN_REVIEW"), "boundary_test": gates.get("boundary_test", "H010_BOUNDARY_PERMISSION_TEST"), "pilot": gates.get("pilot", "H020_PILOT_REVIEW"), "final_audit": gates.get("final_audit", "Z999_FINAL_AUDIT")}

    for name, task_id in required.items():
        if task_id not in tasks:
            errors.append({"type": "missing_required_review_gate", "gate": name, "task_id": task_id, "gate_mode": gate_mode})

    for gate_name in ("start", "setup", "plan", "pilot"):
        task_id = required.get(gate_name)
        task = tasks.get(task_id) if task_id else None
        if task and task["status"] not in {"review_pending", "passed", "blocked"}:
            errors.append({"type": "manual_gate_must_be_review_pending_passed_or_blocked", "gate": gate_name, "task_id": task_id, "status": task["status"], "gate_mode": gate_mode})

    edge_set = {(e["from_task"], e["to_task"], e["edge_type"]) for e in edges}

    def task_status(task_id: str | None) -> str | None:
        if not task_id:
            return None
        task = tasks.get(task_id)
        return task["status"] if task is not None else None

    if gate_mode == "strict":
        if (required["plan"], required["setup"], "depends_on") not in edge_set:
            errors.append({"type": "plan_review_must_depend_on_setup_review", "from_task": required["plan"], "to_task": required["setup"]})
        if (required["boundary_test"], required["plan"], "depends_on") not in edge_set:
            errors.append({"type": "boundary_test_must_depend_on_plan_review", "from_task": required["boundary_test"], "to_task": required["plan"]})
        if (required["pilot"], "F001_QC", "depends_on") not in edge_set and "F001_QC" in tasks:
            errors.append({"type": "pilot_review_must_depend_on_first_qc", "from_task": required["pilot"], "to_task": "F001_QC"})
        bulk_gate = required["pilot"]
        guard_status = task_status(required["pilot"])
    elif gate_mode == "balanced":
        if (required["boundary_test"], required["start"], "depends_on") not in edge_set:
            errors.append({"type": "boundary_test_must_depend_on_start_review", "from_task": required["boundary_test"], "to_task": required["start"]})
        if (required["pilot"], "F001_QC", "depends_on") not in edge_set and "F001_QC" in tasks:
            errors.append({"type": "pilot_review_must_depend_on_first_qc", "from_task": required["pilot"], "to_task": "F001_QC"})
        bulk_gate = required["pilot"]
        guard_status = task_status(required["pilot"])
    else:
        if (required["boundary_test"], required["start"], "depends_on") not in edge_set:
            errors.append({"type": "boundary_test_must_depend_on_start_review", "from_task": required["boundary_test"], "to_task": required["start"]})
        bulk_gate = "F001_QC"
        guard_status = task_status("F001_QC")

    if expected >= 2:
        for idx in range(2, expected + 1):
            spec = f"F{idx:03d}_SPEC"
            if spec in tasks and (spec, bulk_gate, "depends_on") not in edge_set:
                errors.append({"type": "bulk_task_not_gated_by_required_guard", "task_id": spec, "required_gate": bulk_gate, "gate_mode": gate_mode})
                break

    if guard_status != "passed":
        leaked = [tid for tid, task in tasks.items() if tid.startswith("F") and tid[1:4].isdigit() and int(tid[1:4]) >= 2 and task["status"] in {"ready", "running", "passed"}]
        if leaked:
            errors.append({"type": "bulk_tasks_released_before_required_guard", "guard": bulk_gate, "guard_status": guard_status, "example_task_ids": leaked[:10], "gate_mode": gate_mode})

def find_cycles(edges: list[Any], tasks: dict[str, Any]) -> list[list[str]]:
    graph: dict[str, list[str]] = {tid: [] for tid in tasks}
    for edge in edges:
        if edge["edge_type"] in GATING_EDGE_TYPES and edge["from_task"] in tasks and edge["to_task"] in tasks:
            graph[edge["from_task"]].append(edge["to_task"])
    cycles: list[list[str]] = []
    visiting: set[str] = set()
    visited: set[str] = set()
    stack: list[str] = []

    def dfs(node: str) -> None:
        if node in visiting:
            i = stack.index(node) if node in stack else 0
            cycle = stack[i:] + [node]
            if cycle not in cycles:
                cycles.append(cycle)
            return
        if node in visited:
            return
        visiting.add(node)
        stack.append(node)
        for nxt in graph.get(node, []):
            dfs(nxt)
        stack.pop()
        visiting.remove(node)
        visited.add(node)

    for node in sorted(graph):
        dfs(node)
    return cycles


def print_validation_report(report: dict[str, list[dict[str, Any]]]) -> None:
    if not report["errors"] and not report["warnings"]:
        print("Graph validation passed: no errors or warnings.")
        return
    if report["errors"]:
        print("Errors:")
        for item in report["errors"]:
            print("- " + json.dumps(item, ensure_ascii=False))
    if report["warnings"]:
        print("Warnings:")
        for item in report["warnings"]:
            print("- " + json.dumps(item, ensure_ascii=False))


def build_contract_goal_text(contract: dict[str, Any]) -> str:
    project = contract.get("project", {}) or {}
    dod = contract.get("definition_of_done") or []
    gates = contract.get("human_review_gates") or []
    stops = contract.get("stop_conditions") or []
    verification = contract.get("verification", {}) or {}
    required_checks = verification.get("required_checks") or []
    goal = (
        f"/goal Complete the contract-gated Autopilot NodeKit project {project.get('name', '')}. "
        f"Objective: {contract.get('goal', '')}. "
        f"Definition of Done: {'; '.join(str(x) for x in dod[:6])}. "
        f"Human gates are mandatory: {', '.join(str(g.get('id')) for g in gates if isinstance(g, dict))}. "
        f"Verifier is authoritative; required checks: {'; '.join(str(x) for x in required_checks[:6])}. "
        f"Santa dual-review is mandatory for non-human task pass results: reviewer_a=NICE and reviewer_b=NICE. "
        f"Use NodeKit commands for control: validate --strict, background-doctor, launch-background, worker-loop, operator-step, approve-setup, approve-plan, approve-pilot, metrics. "
        f"Stop if: {'; '.join(str(x) for x in stops[:5])}. "
        "Never fabricate data, never bypass review_pending gates, and never mark a task complete from LLM self-report without verifier evidence."
    )
    return goal[:3898].rstrip() + ("…" if len(goal) > 3898 else "")


def doctor(workspace: Path) -> int:
    import shutil

    tools = ["python", "git", "tmux", "codex"]
    rows = []
    for tool in tools:
        path = shutil.which(tool)
        rows.append((tool, "available" if path else "missing", path or ""))
    print(render_table(rows, ["tool", "status", "path"]))
    print("\nRequired for core kit: python. Recommended for Codex-native use: git, tmux, codex.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
