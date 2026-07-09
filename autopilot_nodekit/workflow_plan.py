from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from .figure_plan import santa_review_policy, write_review_files
from .goal_contract import write_goal_contract, ensure_memory_dirs
from .setup_config import write_project_setup
from .util import dump_yaml, workspace_paths

VALID_GATE_MODES = {"fast", "balanced", "strict"}

DEFAULT_STAGES = [
    "Source registry and project physical/technical contract",
    "Builders, validators, and structured evidence framework",
    "Main workflow/notebook/modules and calculation matrix",
    "Smoke tests, verifiers, full-run plan, and final audit package",
]


def generate_workflow_manifest(
    *,
    artifact_count: int = 4,
    project_name: str = "autopilot-workflow-project",
    project_type: str = "science_workflow",
    goal: str = "Build a verifier-backed workflow package.",
    output_dir: str = "outputs/workflow",
    tasks_per_artifact: int = 3,
    gate_mode: str = "balanced",
    stage_names: Optional[List[str]] = None,
    project_spec: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    if artifact_count < 1:
        artifact_count = 1
    if tasks_per_artifact not in {2, 3, 4}:
        raise ValueError("tasks_per_artifact must be 2, 3, or 4")
    gate_mode = (gate_mode or "balanced").strip().lower()
    if gate_mode not in VALID_GATE_MODES:
        raise ValueError("gate_mode must be fast, balanced, or strict")
    stage_names = list(stage_names or [])
    while len(stage_names) < artifact_count:
        stage_names.append(DEFAULT_STAGES[len(stage_names) % len(DEFAULT_STAGES)])
    tasks: List[Dict[str, Any]] = []
    if gate_mode == "strict":
        tasks.append(_setup_review_task())
        tasks.append(_plan_review_task(depends_on=["G000_SETUP_REVIEW"]))
        boundary_depends = ["H000_PLAN_REVIEW"]
        initial_manual = ["G000_SETUP_REVIEW", "H000_PLAN_REVIEW"]
    else:
        tasks.append(_start_review_task(gate_mode))
        boundary_depends = ["G000_START_REVIEW"]
        initial_manual = ["G000_START_REVIEW"]
    tasks.append(_boundary_task(boundary_depends, project_type=project_type))
    tasks.extend(_stage_tasks(1, stage_names[0], depends_on=["H010_BOUNDARY_PERMISSION_TEST"], output_dir=output_dir, tasks_per_artifact=tasks_per_artifact, priority_base=9800))
    if gate_mode in {"balanced", "strict"}:
        tasks.append(_pilot_review_task(project_type=project_type))
        bulk_depends = ["H020_PILOT_REVIEW"]
        pilot_policy = "manual_human_gate"
    else:
        bulk_depends = ["F001_QC"]
        pilot_policy = "automatic_f001_qc_guard"
    for idx in range(2, artifact_count + 1):
        tasks.extend(_stage_tasks(idx, stage_names[idx - 1], depends_on=bulk_depends, output_dir=output_dir, tasks_per_artifact=tasks_per_artifact, priority_base=max(1000, 9600 - idx * 10)))
    qc_ids = [f"F{i:03d}_QC" for i in range(1, artifact_count + 1)]
    tasks.append(_final_audit_task(qc_ids=qc_ids, project_type=project_type))
    review_gates: Dict[str, str] = {"boundary_test": "H010_BOUNDARY_PERMISSION_TEST", "final_audit": "Z999_FINAL_AUDIT"}
    if gate_mode == "strict":
        review_gates.update({"setup": "G000_SETUP_REVIEW", "plan": "H000_PLAN_REVIEW", "pilot": "H020_PILOT_REVIEW"})
    else:
        review_gates["start"] = "G000_START_REVIEW"
        if gate_mode == "balanced":
            review_gates["pilot"] = "H020_PILOT_REVIEW"
        else:
            review_gates["automatic_pilot_guard"] = "F001_QC"
    return {
        "project": {
            "name": project_name,
            "goal": goal,
            "project_spec": "PROJECT_SPEC.yml" if project_spec else None,
            "setup_config": "PROJECT_SETUP.yml",
            "setup_required": True,
            "goal_contract": "GOAL_CONTRACT.yml",
            "goal_contract_required": True,
            "plan_type": project_type,
            "artifact_kind": "workflow_stage",
            "artifact_count": artifact_count,
            "output_dir": output_dir,
            "tasks_per_artifact": tasks_per_artifact,
            "task_scale": {2: "smoke", 3: "standard", 4: "prod"}[tasks_per_artifact],
            "gate_mode": gate_mode,
            "pilot_policy": pilot_policy,
            "minimum_task_count": len(tasks),
            "actual_task_count": len(tasks),
            "initial_manual_gates": initial_manual,
            "initial_approval_command": "python -m autopilot_nodekit approve-start --workspace ." if gate_mode != "strict" else "python -m autopilot_nodekit approve-setup --workspace . && python -m autopilot_nodekit approve-plan --workspace .",
            "review_gates": review_gates,
            "automation_bias": "After approved gates pass, keep the background worker looping. Notify humans only for human gates, repeated repair failure, queue stalls, process death, or explicit external-job approvals.",
        },
        "tasks": tasks,
    }


def write_project_manifest(workspace: Path, manifest: Dict[str, Any], spec: Optional[Dict[str, Any]] = None) -> None:
    paths = workspace_paths(workspace)
    paths["automation"].mkdir(parents=True, exist_ok=True)
    dump_yaml(paths["manifest"], manifest)
    project = manifest.get("project", {}) or {}
    setup = _generic_setup(project)
    write_project_setup(workspace, setup)
    contract = _generic_contract(project, manifest)
    write_goal_contract(workspace, contract)
    ensure_memory_dirs(workspace)
    write_review_files(workspace, manifest)


def _start_review_task(gate_mode: str) -> Dict[str, Any]:
    return {
        "id": "G000_START_REVIEW",
        "title": "Human review: approve project spec, setup, contract, and manifest",
        "objective": "Approve the combined startup surface before background loop begins. Confirm this is not a demo/figure-template plan unless explicitly intended.",
        "success_criteria": "Human approval event exists after reviewing PROJECT_SPEC.md, SETUP_REVIEW.md, GOAL_CONTRACT.md, TASK_REVIEW.md, REQUIREMENTS_LOCK.md, .nodekit wrappers, AGENTS.md, and .agents/skills.",
        "status": "review_pending",
        "priority": 11000,
        "max_attempts": 1,
        "input_files": ["PROJECT_SPEC.yml", "PROJECT_SETUP.yml", "GOAL_CONTRACT.yml", "TASK_REVIEW.md", "REQUIREMENTS_LOCK.md", ".nodekit", "AGENTS.md"],
        "expected_outputs": ["automation/events.jsonl", "project_memory/rules.md"],
        "done_when": ["startup files reviewed", "demo/template contamination excluded", "approval event exists"],
        "human_review_required": True,
    }


def _setup_review_task() -> Dict[str, Any]:
    t = _start_review_task("strict")
    t["id"] = "G000_SETUP_REVIEW"
    t["title"] = "Human review: approve Layer 0 setup and runtime wrappers"
    return t


def _plan_review_task(depends_on: List[str]) -> Dict[str, Any]:
    t = _start_review_task("strict")
    t["id"] = "H000_PLAN_REVIEW"
    t["title"] = "Human review: approve task manifest and DAG"
    t["depends_on"] = depends_on
    return t


def _boundary_task(depends_on: List[str], *, project_type: str) -> Dict[str, Any]:
    return {
        "id": "H010_BOUNDARY_PERMISSION_TEST",
        "title": "Boundary, runtime, and worker adapter test",
        "objective": "Verify NodeKit wrappers, background backend, worker.command, Codex CLI config, hook platform compatibility, permission boundaries, and strict graph validation before business tasks.",
        "success_criteria": "background-doctor checks are clean, strict graph validation passes, and worker command is non-empty and platform-compatible.",
        "depends_on": depends_on,
        "priority": 9900,
        "max_attempts": 2,
        "verifier": {"command": "python -m autopilot_nodekit background-doctor --workspace . --json && python -m autopilot_nodekit validate --workspace . --strict"},
        "input_files": ["PROJECT_SPEC.yml", "PROJECT_SETUP.yml", "GOAL_CONTRACT.yml", "automation/config.yml", ".nodekit", ".codex/config.toml", ".codex/hooks.json"],
        "expected_outputs": ["logs/raw/boundary_permission_test.md", "project_memory/rules.md", "automation/background"],
        "done_when": ["worker.command non-empty", "NodeKit import works", "Codex config has no invalid timeout=0", "hook is platform-compatible", "strict validation passes"],
        "forbidden": ["write outside workspace", "launch multiple duplicate workers", "submit external jobs during boundary test"],
        "review_policy": santa_review_policy(),
        "memory": {"required_tags": ["boundary", "bootstrap", "background", "worker", project_type], "required_scopes": ["project", "tool", "decision"], "search_queries": ["background worker command codex config hook pythonpath"]},
    }


def _pilot_review_task(*, project_type: str) -> Dict[str, Any]:
    return {
        "id": "H020_PILOT_REVIEW",
        "title": "Human review: approve first workflow stage before bulk loop",
        "objective": "Inspect F001 outputs, verifier evidence, and Santa review before releasing later workflow stages.",
        "success_criteria": "Human approval event exists after F001_QC passes.",
        "depends_on": ["F001_QC"],
        "status": "review_pending",
        "priority": 9700,
        "max_attempts": 1,
        "input_files": ["tasks/F001", "runs/", "memory/nodes"],
        "expected_outputs": ["project_memory/human_feedback.md", "automation/events.jsonl"],
        "done_when": ["F001 reviewed", "approval event exists"],
        "human_review_required": True,
    }


def _stage_tasks(index: int, name: str, *, depends_on: List[str], output_dir: str, tasks_per_artifact: int, priority_base: int) -> List[Dict[str, Any]]:
    fid = f"F{index:03d}"
    task_dir = f"tasks/{fid}"
    review = santa_review_policy()
    tasks: List[Dict[str, Any]] = [
        {
            "id": f"{fid}_SPEC",
            "artifact_id": fid,
            "phase": "spec",
            "title": f"{fid}: specify {name}",
            "objective": f"Define scope, inputs, outputs, verifier, risks, and physical/technical assumptions for workflow stage: {name}.",
            "success_criteria": "A concrete stage contract exists and is verifiable.",
            "depends_on": depends_on,
            "priority": priority_base,
            "max_attempts": 3,
            "input_files": ["PROJECT_SPEC.yml", "GOAL_CONTRACT.yml", "project_memory/rules.md"],
            "expected_outputs": [f"{task_dir}/spec.yml", f"{task_dir}/task_memory.md"],
            "done_when": ["inputs and source-of-truth are listed", "expected outputs are listed", "verifier is specified", "Santa dual-review returns NICE/NICE"],
            "review_policy": review,
            "memory": {"required_tags": [fid.lower(), "workflow", "spec"], "required_scopes": ["project", "decision", "task"], "search_queries": [name]},
        },
        {
            "id": f"{fid}_BUILD",
            "artifact_id": fid,
            "phase": "build",
            "title": f"{fid}: build {name}",
            "objective": f"Create the concrete files, scripts, notebook cells, plans, or reports for {name} according to the approved spec.",
            "success_criteria": "Expected stage artifacts exist and evidence is recorded.",
            "depends_on": [f"{fid}_SPEC"],
            "priority": priority_base - 1,
            "max_attempts": 4,
            "input_files": [f"{task_dir}/spec.yml"],
            "expected_outputs": [f"{task_dir}/evidence.md", output_dir],
            "done_when": ["artifact files or reports exist", "commands and limitations are recorded", "no placeholder result is declared complete", "Santa dual-review returns NICE/NICE"],
            "review_policy": review,
            "memory": {"required_task_ids": [f"{fid}_SPEC"], "required_tags": [fid.lower(), "workflow", "build"], "required_scopes": ["task", "tool", "bug"], "search_queries": [name]},
        },
        {
            "id": f"{fid}_QC",
            "artifact_id": fid,
            "phase": "qc",
            "title": f"{fid}: verify and correct {name}",
            "objective": f"Verify outputs for {name}, record failures, and insert focused repair tasks for unresolved issues.",
            "success_criteria": "Stage QC passes with evidence and no unresolved blockers.",
            "depends_on": [f"{fid}_BUILD"],
            "priority": priority_base - 2,
            "max_attempts": 4,
            "verifier": {"command": "python -m autopilot_nodekit validate --workspace . --strict"},
            "input_files": [f"{task_dir}/spec.yml", f"{task_dir}/evidence.md"],
            "expected_outputs": [f"{task_dir}/qc.md", f"{task_dir}/evidence.md"],
            "done_when": ["strict validation passes", "stage-specific checks are recorded", "repair tasks exist for unresolved issues", "Santa dual-review returns NICE/NICE"],
            "review_policy": review,
            "memory": {"required_task_ids": [f"{fid}_SPEC", f"{fid}_BUILD"], "required_tags": [fid.lower(), "workflow", "qc"], "required_scopes": ["task", "bug", "decision"], "search_queries": [name]},
        },
    ]
    if tasks_per_artifact >= 4:
        validate_task = {
            "id": f"{fid}_VALIDATE",
            "artifact_id": fid,
            "phase": "validate",
            "title": f"{fid}: domain validation for {name}",
            "objective": f"Run deterministic/domain validation before QC for {name}.",
            "success_criteria": "Domain validation evidence is recorded; unresolved issues become repair tasks.",
            "depends_on": [f"{fid}_BUILD"],
            "priority": priority_base - 2,
            "max_attempts": 3,
            "input_files": [f"{task_dir}/evidence.md"],
            "expected_outputs": [f"{task_dir}/validation.md"],
            "done_when": ["validation evidence exists", "limitations are recorded", "Santa dual-review returns NICE/NICE"],
            "review_policy": review,
        }
        tasks.insert(2, validate_task)
        tasks[-1]["depends_on"] = [f"{fid}_VALIDATE"]
    elif tasks_per_artifact == 2:
        tasks[1]["id"] = f"{fid}_QC"
        tasks[1]["phase"] = "build_qc"
        tasks[1]["title"] = f"{fid}: build, verify, and correct {name}"
        tasks = [tasks[0], tasks[1]]
    return tasks


def _final_audit_task(*, qc_ids: List[str], project_type: str) -> Dict[str, Any]:
    return {
        "id": "Z999_FINAL_AUDIT",
        "title": "Final audit: workflow deliverables verified",
        "objective": "Check all workflow stages, verifier evidence, Santa review records, metrics, and unresolved blockers before delivery.",
        "success_criteria": "All QC tasks passed, strict validation passes, metrics exist, and final audit report is written.",
        "depends_on": qc_ids,
        "priority": 100,
        "max_attempts": 2,
        "verifier": {"command": "python -m autopilot_nodekit validate --workspace . --strict"},
        "input_files": ["PROJECT_SPEC.yml", "automation/manifest.yml", "runs/", "memory/nodes"],
        "expected_outputs": ["automation/final_audit.md", "automation/metrics.json", "automation/metrics.md"],
        "done_when": ["all QC tasks passed", "strict validation passes", "metrics exist", "no unresolved blockers"],
        "review_policy": santa_review_policy(),
    }


def _generic_setup(project: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "version": 1,
        "project": {"name": project.get("name"), "kind": project.get("plan_type"), "artifact_count": project.get("artifact_count"), "gate_mode": project.get("gate_mode")},
        "inputs": {"required_roots": ["."], "missing_input_policy": "Block or insert a source-discovery task; never fabricate data or results."},
        "outputs": {"required_roots": [project.get("output_dir", "outputs/workflow"), "tasks", "project_memory", "logs/raw", "runs", "memory/nodes", "automation"]},
        "codex_native_files": ["AGENTS.md", ".agents/skills", ".codex/config.toml", ".codex/agents", ".codex/hooks.json", ".nodekit"],
        "permissions": {"sandbox": "workspace-write", "write_deny": [".git", "automation/autopilot.sqlite"]},
        "verifier": {"startup": "python -m autopilot_nodekit background-doctor --workspace . --json && python -m autopilot_nodekit validate --workspace . --strict"},
        "human_gate": {"approval_command": project.get("initial_approval_command")},
    }


def _generic_contract(project: Dict[str, Any], manifest: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "version": 1,
        "project": {"name": project.get("name"), "type": project.get("plan_type"), "artifact_kind": "workflow_stage", "artifact_count": project.get("artifact_count"), "minimum_task_count": project.get("minimum_task_count"), "gate_mode": project.get("gate_mode")},
        "goal": project.get("goal"),
        "definition_of_done": ["Every stage QC task passed", "Verifier evidence exists", "Santa NICE/NICE exists for non-human pass", "Final audit passes", "No placeholder or unverified result is presented as complete"],
        "forbidden": ["Do not fabricate data/results", "Do not bypass NodeKit verifier/Santa review", "Do not edit automation/autopilot.sqlite manually", "Do not launch duplicate background workers"],
        "human_review_gates": project.get("review_gates"),
        "stop_conditions": ["human gate pending", "worker/background process exits", "same repair fails repeatedly", "external job submission requires human approval", "strict validation fails"],
        "review_policy": {"method": "santa_dual_review", "required_for_non_human_pass": True},
    }
