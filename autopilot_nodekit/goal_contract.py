from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List

from .util import dump_yaml, load_yaml, read_text, write_text, workspace_paths

CONTRACT_FILENAME = "GOAL_CONTRACT.yml"
CONTRACT_REVIEW_FILENAME = "GOAL_CONTRACT.md"

REQUIRED_TOP_LEVEL = [
    "setup",
    "goal",
    "inputs",
    "outputs",
    "definition_of_done",
    "forbidden",
    "human_review_gates",
    "stop_conditions",
    "permissions",
    "verification",
    "repair_policy",
    "observability",
]

REQUIRED_DOD_ITEMS = [
    "Every deliverable has source inputs or an explicit human-approved missing-input exception.",
    "Every deliverable has a reproducible script or build command.",
    "Expected output files exist and pass artifact verification.",
    "Verifier evidence is recorded before a task is treated as complete.",
    "No placeholder, fabricated, or unverified artifact is marked complete.",
]


def contract_path(workspace: Path) -> Path:
    return workspace.resolve() / CONTRACT_FILENAME


def contract_review_path(workspace: Path) -> Path:
    return workspace.resolve() / CONTRACT_REVIEW_FILENAME


def load_goal_contract(workspace: Path, default: Dict[str, Any] | None = None) -> Dict[str, Any]:
    path = contract_path(workspace)
    if not path.exists():
        return default or {}
    return load_yaml(path)


def write_goal_contract(workspace: Path, contract: Dict[str, Any]) -> None:
    workspace = workspace.resolve()
    dump_yaml(contract_path(workspace), contract)
    write_text(contract_review_path(workspace), render_goal_contract_review(contract))


def build_figure_goal_contract(
    *,
    figure_count: int,
    journal: str,
    project_name: str = "journal-figure-batch",
    output_dir: str = "outputs/figures",
    data_dir: str = "data",
    script_dir: str = "scripts/figures",
    tasks_per_figure: int = 3,
    gate_mode: str = "strict",
) -> Dict[str, Any]:
    gate_mode = (gate_mode or "strict").strip().lower()
    if gate_mode not in {"fast", "balanced", "strict"}:
        raise ValueError("gate_mode must be fast, balanced, or strict")
    if figure_count < 1:
        raise ValueError("figure_count must be >= 1")
    gate_extra = 5 if gate_mode == "strict" else 4 if gate_mode == "balanced" else 3
    min_tasks = figure_count * max(2, tasks_per_figure) + gate_extra
    if gate_mode == "strict":
        human_review_gates = [
            {"id": "G000_SETUP_REVIEW", "name": "Layer 0 files, skills, subagents, permissions, and verifier setup review", "required_before": "task_plan_review", "approval_command": "python -m autopilot_nodekit approve-setup --workspace ."},
            {"id": "H000_PLAN_REVIEW", "name": "Task list and task scheme review", "required_before": "boundary_permission_test", "approval_command": "python -m autopilot_nodekit approve-plan --workspace ."},
            {"id": "H010_BOUNDARY_PERMISSION_TEST", "name": "Boundary and permission verification", "required_before": "first_artifact_work", "approval_command": "must pass verifier; no manual override in normal use"},
            {"id": "H020_PILOT_REVIEW", "name": "First complete figure / journal-fit review", "required_before": "bulk_loop", "approval_command": "python -m autopilot_nodekit approve-pilot --workspace ."},
            {"id": "Z999_FINAL_AUDIT", "name": "Final all-figure audit", "required_before": "delivery", "approval_command": "must pass verifier and any final human spot-check policy"},
        ]
    elif gate_mode == "balanced":
        human_review_gates = [
            {"id": "G000_START_REVIEW", "name": "Combined startup review: project spec, Layer 0, contract, task manifest, permissions, and loop mode", "required_before": "boundary_permission_test", "approval_command": "python -m autopilot_nodekit approve-start --workspace ."},
            {"id": "H010_BOUNDARY_PERMISSION_TEST", "name": "Boundary and permission verification", "required_before": "first_artifact_work", "approval_command": "must pass verifier; no manual override in normal use"},
            {"id": "H020_PILOT_REVIEW", "name": "First complete figure / journal-fit review", "required_before": "bulk_loop", "approval_command": "python -m autopilot_nodekit approve-pilot --workspace ."},
            {"id": "Z999_FINAL_AUDIT", "name": "Final all-figure audit", "required_before": "delivery", "approval_command": "must pass verifier and any final human spot-check policy"},
        ]
    else:
        human_review_gates = [
            {"id": "G000_START_REVIEW", "name": "Combined startup review: project spec, Layer 0, contract, task manifest, permissions, and loop mode", "required_before": "boundary_permission_test", "approval_command": "python -m autopilot_nodekit approve-start --workspace ."},
            {"id": "H010_BOUNDARY_PERMISSION_TEST", "name": "Boundary and permission verification", "required_before": "first_artifact_work", "approval_command": "must pass verifier; no manual override in normal use"},
            {"id": "F001_QC", "name": "Automatic first-figure pilot guard", "required_before": "bulk_loop", "approval_command": "automatic: F001_QC must pass verifier and Santa NICE/NICE"},
            {"id": "Z999_FINAL_AUDIT", "name": "Final all-figure audit", "required_before": "delivery", "approval_command": "must pass verifier and any final human spot-check policy"},
        ]
    return {
        "version": 1,
        "project": {
            "name": project_name,
            "type": "journal_figures",
            "artifact_kind": "figure",
            "artifact_count": figure_count,
            "journal": journal,
            "minimum_task_count": min_tasks,
            "gate_mode": gate_mode,
        },
        "setup": {
            "layer": 0,
            "file": "PROJECT_SETUP.yml",
            "review_file": "SETUP_REVIEW.md",
            "gate": "G000_START_REVIEW" if gate_mode in {"fast", "balanced"} else "G000_SETUP_REVIEW",
            "gate_mode": gate_mode,
            "purpose": "Configure required files, skills, Codex subagents, permissions, verifier commands, output directories, and the selected human-gate mode before approving the task manifest.",
        },
        "goal": f"Produce {figure_count} publication-ready figures for {journal} with reproducible sources, scripts, exports, captions, verification evidence, and review gates.",
        "inputs": {
            "required_roots": [data_dir],
            "per_figure_expected": [
                f"{data_dir}/<figure_id>.* or an approved documented source-location decision",
                "journal formatting requirements or project-level journal rule memory",
            ],
        },
        "outputs": {
            "required_roots": [output_dir, script_dir, "tasks", "project_memory", "logs/raw", "runs", "memory/nodes"],
            "per_figure_expected": [
                f"{output_dir}/<figure_id>.pdf",
                f"{output_dir}/<figure_id>.png",
                f"{output_dir}/<figure_id>.svg",
                f"{script_dir}/plot_<figure_id>.py",
                "tasks/<figure_id>/evidence.md",
                "tasks/<figure_id>/task_memory.md",
                "tasks/<figure_id>/caption.md",
                "tasks/<figure_id>/journal_check.md",
            ],
        },
        "definition_of_done": REQUIRED_DOD_ITEMS
        + [
            "Axis labels, units, scale bars, legends, captions, and journal sizing checks are recorded when applicable.",
            "Final audit confirms every figure QC task passed and unresolved blockers are zero.",
        ],
        "forbidden": [
            "Do not fabricate data, labels, captions, or provenance.",
            "Do not create placeholder figures and mark them complete.",
            "Do not mark complete or passed from worker self-report alone; verifier evidence is authoritative.",
            "Do not bypass review_pending tasks by editing SQLite directly.",
            "Do not write outside allowed output, task, log, run, and memory paths unless the boundary test explicitly approves it.",
        ],
        "human_review_gates": human_review_gates,
        "stop_conditions": [
            "No clear Definition of Done exists.",
            "Required input data or journal rule is missing and no human-approved exception exists.",
            "Verifier cannot run or returns invalid output.",
            "A task reaches max_attempts without a new repair hypothesis.",
            "A proposed action is outside the approved permission boundary.",
            "The same failure signature recurs at least twice after repair.",
            "A required Santa dual-review is missing or either reviewer returns NAUGHTY.",
            "Any required human review gate for the selected gate_mode is pending or rejected.",
        ],
        "permissions": {
            "read_allow": [".", data_dir, "project_memory", "automation", "memory", "runs"],
            "write_allow": [output_dir, script_dir, "tasks", "project_memory", "logs/raw", "runs", "memory/nodes", "automation"],
            "write_deny": ["data/raw", ".git", "automation/autopilot.sqlite", "GOAL_CONTRACT.yml"],
            "sandbox": "workspace-write",
        },
        "review_policy": {
            "method": "santa_dual_review",
            "required_for_non_human_pass": True,
            "reviewers": ["autopilot-santa-reviewer-a", "autopilot-santa-reviewer-b"],
            "rule": "A non-human task can only pass when verifier succeeds and both independent reviewers return NICE.",
        },
        "verification": {
            "authoritative": True,
            "required_checks": [
                "artifact files exist and are non-empty",
                "plot/build script can reproduce the artifact or failure is blocked with evidence",
                "journal format check evidence exists",
                "caption/provenance evidence exists",
                "manifest graph validation passes",
            ],
            "default_commands": [
                "python -m autopilot_nodekit validate --workspace . --strict",
                f"python -m autopilot_nodekit verify-artifact --workspace . --glob '{output_dir}/F001*' --min-bytes 512",
            ],
        },
        "repair_policy": {
            "max_iterations_per_task": 4,
            "failure_fields_required": ["failure_reason", "responsible_files", "patch_summary", "verifier_output"],
            "must_insert_repair_task_on_qc_failure": True,
            "escalate_repeated_failure_after": 2,
            "memory_files": ["project_memory/failures.md", "tasks/<figure_id>/task_memory.md", "tasks/<figure_id>/evidence.md"],
        },
        "observability": {
            "event_log": "automation/events.jsonl",
            "sqlite": "automation/autopilot.sqlite",
            "live_manifest": "automation/manifest.live.md",
            "metrics_report": "automation/metrics.json",
            "raw_logs": "logs/raw/",
            "replay_inputs": ["runs/<run_id>/prompt.md", "runs/<run_id>/context_pack.json", "runs/<run_id>/worker_result.normalized.json", "runs/<run_id>/control_result.json"],
        },
        "required_user_flow": [
            "0_generate_or_review_project_spec_and_layer0_setup",
            "1_approve_minimal_required_human_gate_for_gate_mode",
            "2_run_boundary_permission_test",
            "3_first_figure_pilot_guard_or_review",
            "4_bulk_loop_repair_self_iterate_final_verify",
        ],
    }


def render_goal_contract_review(contract: Dict[str, Any]) -> str:
    project = contract.get("project", {}) or {}
    lines = [
        "# Goal Contract Review",
        "",
        "This contract is the highest-level source of truth for the loop. If it is incomplete, do not enter the automated loop.",
        "",
        "## Project",
        "",
        f"- name: `{project.get('name', '')}`",
        f"- type: `{project.get('type', '')}`",
        f"- artifact_count: `{project.get('artifact_count', '')}`",
        f"- journal: `{project.get('journal', '')}`",
        f"- minimum_task_count: `{project.get('minimum_task_count', '')}`",
        "",
        "## Goal",
        "",
        str(contract.get("goal", "")),
        "",
    ]
    for key in ["setup", "inputs", "outputs", "definition_of_done", "forbidden", "human_review_gates", "stop_conditions", "permissions", "review_policy", "verification", "repair_policy", "observability", "required_user_flow"]:
        value = contract.get(key)
        lines += [f"## {key}", "", _render_value(value), ""]
    lines += [
        "## Strong commands",
        "",
        "```bash",
        "python -m autopilot_nodekit validate --workspace . --strict",
        "python -m autopilot_nodekit background-doctor --workspace .",
        "python -m autopilot_nodekit launch-background --workspace . --worker-id codex-worker --max-cycles 0",
        "python -m autopilot_nodekit metrics --workspace .",
        "```",
        "",
        "`next-command`, `status`, and `background-status` are diagnostic commands. Normal background runs should let the worker/operator handle routine progress.",
        "",
    ]
    return "\n".join(lines)


def _render_value(value: Any) -> str:
    if isinstance(value, list):
        out = []
        for item in value:
            if isinstance(item, dict):
                out.append("- " + json.dumps(item, ensure_ascii=False))
            else:
                out.append(f"- {item}")
        return "\n".join(out) or "(empty)"
    if isinstance(value, dict):
        lines = []
        for k, v in value.items():
            if isinstance(v, (list, dict)):
                lines.append(f"- `{k}`: {json.dumps(v, ensure_ascii=False)}")
            else:
                lines.append(f"- `{k}`: {v}")
        return "\n".join(lines) or "(empty)"
    return str(value or "(empty)")


def validate_goal_contract(contract: Dict[str, Any], *, manifest: Dict[str, Any] | None = None) -> Dict[str, List[Dict[str, Any]]]:
    errors: List[Dict[str, Any]] = []
    warnings: List[Dict[str, Any]] = []
    if not contract:
        errors.append({"type": "missing_goal_contract", "path": CONTRACT_FILENAME})
        return {"errors": errors, "warnings": warnings}
    for key in REQUIRED_TOP_LEVEL:
        value = contract.get(key)
        if _is_empty(value):
            errors.append({"type": "contract_missing_required_field", "field": key})
    dod = contract.get("definition_of_done") or []
    if isinstance(dod, str):
        dod = [dod]
    if len(dod) < 4:
        errors.append({"type": "definition_of_done_too_weak", "minimum_items": 4, "actual_items": len(dod) if isinstance(dod, list) else 0})
    gates = contract.get("human_review_gates") or []
    gate_ids = {str(g.get("id")) for g in gates if isinstance(g, dict) and g.get("id")}
    gate_mode = str((contract.get("project") or {}).get("gate_mode") or "strict")
    if gate_mode == "fast":
        required_gates = ["G000_START_REVIEW", "H010_BOUNDARY_PERMISSION_TEST", "F001_QC", "Z999_FINAL_AUDIT"]
    elif gate_mode == "balanced":
        required_gates = ["G000_START_REVIEW", "H010_BOUNDARY_PERMISSION_TEST", "H020_PILOT_REVIEW", "Z999_FINAL_AUDIT"]
    else:
        required_gates = ["G000_SETUP_REVIEW", "H000_PLAN_REVIEW", "H010_BOUNDARY_PERMISSION_TEST", "H020_PILOT_REVIEW", "Z999_FINAL_AUDIT"]
    for required_gate in required_gates:
        if required_gate not in gate_ids:
            errors.append({"type": "contract_missing_required_gate", "gate": required_gate, "gate_mode": gate_mode})
    forbidden = "\n".join(str(x) for x in (contract.get("forbidden") or []))
    if "fabricat" not in forbidden.lower() and "伪造" not in forbidden:
        warnings.append({"type": "contract_should_explicitly_forbid_fabrication"})
    if manifest:
        project = manifest.get("project", {}) or {}
        tasks = manifest.get("tasks", []) or []
        min_count = int((contract.get("project") or {}).get("minimum_task_count") or project.get("minimum_task_count") or 0)
        if min_count and len(tasks) < min_count:
            errors.append({"type": "manifest_below_contract_minimum_task_count", "minimum_task_count": min_count, "actual_task_count": len(tasks)})
        for idx, task in enumerate(tasks):
            if not isinstance(task, dict):
                continue
            task_id = str(task.get("id") or idx)
            for field in ["objective", "success_criteria"]:
                if _is_empty(task.get(field)):
                    errors.append({"type": "task_missing_required_field", "task_id": task_id, "field": field})
            contract_fields = task.get("contract") or {}
            for field in ["input_files", "expected_outputs", "done_when"]:
                if _is_empty(task.get(field)) and _is_empty(contract_fields.get(field)):
                    errors.append({"type": "task_missing_verifiable_contract_field", "task_id": task_id, "field": field})
            if not bool(task.get("human_review_required") or contract_fields.get("human_review_required")):
                review_policy = task.get("review_policy") or contract_fields.get("review_policy") or {}
                if not isinstance(review_policy, dict) or review_policy.get("method") != "santa_dual_review" or review_policy.get("required") is not True:
                    errors.append({"type": "task_missing_required_santa_review_policy", "task_id": task_id})
    return {"errors": errors, "warnings": warnings}


def _is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, tuple, set, dict)):
        return len(value) == 0
    return False


def task_contract_from_task(task: Dict[str, Any]) -> Dict[str, Any]:
    contract = dict(task.get("contract") or {})
    for key in ["input_files", "expected_outputs", "done_when", "forbidden", "forbidden_actions", "human_review_required", "permissions", "evidence_files", "artifact_id", "phase", "allowed_write_paths", "review_policy"]:
        if key in task and key not in contract:
            contract[key] = task[key]
    return contract


def ensure_memory_dirs(workspace: Path) -> None:
    for rel in ["project_memory", "logs/raw", "tasks"]:
        (workspace / rel).mkdir(parents=True, exist_ok=True)
    defaults = {
        "project_memory/decisions.md": "# Decisions\n\n",
        "project_memory/failures.md": "# Failure Patterns\n\n",
        "project_memory/rules.md": "# Rules\n\n",
        "project_memory/human_feedback.md": "# Human Feedback\n\n",
    }
    for rel, text in defaults.items():
        path = workspace / rel
        if not path.exists():
            write_text(path, text)
