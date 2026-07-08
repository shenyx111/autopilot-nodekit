from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from .util import dump_yaml, write_text, workspace_paths
from .goal_contract import build_figure_goal_contract, write_goal_contract, ensure_memory_dirs
from .setup_config import build_figure_project_setup, write_project_setup


DEFAULT_OUTPUT_DIR = "outputs/figures"
VALID_GATE_MODES = {"fast", "balanced", "strict"}


def figure_id(index: int) -> str:
    return f"F{index:03d}"


def normalize_gate_mode(gate_mode: str | None) -> str:
    gate_mode = (gate_mode or "strict").strip().lower()
    if gate_mode not in VALID_GATE_MODES:
        raise ValueError(f"gate_mode must be one of {sorted(VALID_GATE_MODES)}, got {gate_mode!r}")
    return gate_mode


def santa_review_policy() -> Dict[str, Any]:
    return {
        "method": "santa_dual_review",
        "required": True,
        "reviewers": ["autopilot-santa-reviewer-a", "autopilot-santa-reviewer-b"],
        "pass_rule": "Both independent reviewers must return NICE in worker_result.review before a pass-like result is accepted.",
    }


def generate_journal_figure_manifest(
    *,
    figure_count: int,
    project_name: str = "journal-figure-batch",
    journal: str = "target journal",
    output_dir: str = DEFAULT_OUTPUT_DIR,
    tasks_per_figure: int = 3,
    min_tasks_per_figure: int = 2,
    gate_mode: str = "strict",
    project_spec: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Generate a review/loop gated figure-production task graph.

    gate_mode controls human stops:
    - fast: one upfront human approval, then boundary test, automatic F001 pilot guard, bulk loop.
    - balanced: one upfront human approval plus human F001 pilot review before bulk loop.
    - strict: separate setup approval, plan approval, and human F001 pilot review.
    """
    if figure_count < 1:
        raise ValueError("figure_count must be >= 1")
    if tasks_per_figure < min_tasks_per_figure:
        raise ValueError(f"tasks_per_figure must be >= {min_tasks_per_figure}")
    if tasks_per_figure not in {2, 3, 4}:
        raise ValueError("tasks_per_figure must be 2, 3, or 4")
    gate_mode = normalize_gate_mode(gate_mode)

    tasks: List[Dict[str, Any]] = []

    if gate_mode == "strict":
        tasks.append(_setup_review_task())
        tasks.append(_plan_review_task(depends_on=["G000_SETUP_REVIEW"]))
        boundary_depends_on = ["H000_PLAN_REVIEW"]
        initial_manual_gates = ["G000_SETUP_REVIEW", "H000_PLAN_REVIEW"]
        approve_command = "python -m autopilot_nodekit approve-setup --workspace . && python -m autopilot_nodekit approve-plan --workspace ."
    else:
        tasks.append(_start_review_task(gate_mode=gate_mode))
        boundary_depends_on = ["G000_START_REVIEW"]
        initial_manual_gates = ["G000_START_REVIEW"]
        approve_command = "python -m autopilot_nodekit approve-start --workspace . --summary 'Project spec, Layer 0 setup, contract, task manifest, permissions, and loop mode reviewed.'"

    tasks.append(_boundary_task(depends_on=boundary_depends_on, output_dir=output_dir))

    # First/pilot figure always runs after the boundary test. In fast mode it is
    # an automatic pilot guard: F002+ depend on F001_QC instead of a manual gate.
    tasks.extend(_figure_tasks(1, depends_on=["H010_BOUNDARY_PERMISSION_TEST"], journal=journal, output_dir=output_dir, tasks_per_figure=tasks_per_figure, priority_base=9800))

    if gate_mode in {"balanced", "strict"}:
        tasks.append(_pilot_review_task(output_dir=output_dir))
        bulk_depends_on = ["H020_PILOT_REVIEW"]
        pilot_policy = "manual_human_gate"
    else:
        bulk_depends_on = ["F001_QC"]
        pilot_policy = "automatic_f001_qc_guard"

    for idx in range(2, figure_count + 1):
        priority_base = max(1000, 9600 - idx * 10)
        tasks.extend(_figure_tasks(idx, depends_on=bulk_depends_on, journal=journal, output_dir=output_dir, tasks_per_figure=tasks_per_figure, priority_base=priority_base))

    qc_ids = [f"{figure_id(i)}_QC" for i in range(1, figure_count + 1)]
    tasks.append(_final_audit_task(figure_count=figure_count, qc_ids=qc_ids))

    min_task_count = figure_count * tasks_per_figure + (len(tasks) - figure_count * tasks_per_figure)
    review_gates: Dict[str, str] = {"boundary_test": "H010_BOUNDARY_PERMISSION_TEST", "final_audit": "Z999_FINAL_AUDIT"}
    if gate_mode == "strict":
        review_gates.update({"setup": "G000_SETUP_REVIEW", "plan": "H000_PLAN_REVIEW", "pilot": "H020_PILOT_REVIEW"})
    else:
        review_gates.update({"start": "G000_START_REVIEW"})
        if gate_mode == "balanced":
            review_gates["pilot"] = "H020_PILOT_REVIEW"
        else:
            review_gates["automatic_pilot_guard"] = "F001_QC"

    required_phases = [
        "0_generate_or_review_project_spec_and_layer0_setup",
        "1_approve_only_the_minimal_required_human_gates",
        "2_run_boundary_permission_test",
        "3_first_figure_pilot_guard",
        "4_bulk_loop_self_correction_final_verification",
    ]
    if gate_mode == "strict":
        required_phases[1] = "1_separate_setup_and_plan_human_reviews"
    elif gate_mode == "balanced":
        required_phases[3] = "3_first_figure_human_pilot_review"
    else:
        required_phases[3] = "3_first_figure_automatic_pilot_guard_no_extra_stop"

    return {
        "project": {
            "name": project_name,
            "goal": f"Produce {figure_count} journal-ready figures for {journal} with Codex/NodeKit loops, verifier authority, Santa review, repair, and auditable memory.",
            "project_spec": "PROJECT_SPEC.yml" if project_spec else None,
            "setup_config": "PROJECT_SETUP.yml",
            "setup_required": True,
            "goal_contract": "GOAL_CONTRACT.yml",
            "goal_contract_required": True,
            "plan_type": "journal_figures",
            "artifact_kind": "figure",
            "artifact_count": figure_count,
            "journal": journal,
            "output_dir": output_dir,
            "tasks_per_artifact": tasks_per_figure,
            "task_scale": {2: "smoke", 3: "standard", 4: "prod"}.get(tasks_per_figure, "standard"),
            "gate_mode": gate_mode,
            "pilot_policy": pilot_policy,
            "minimum_task_count": min_task_count,
            "actual_task_count": len(tasks),
            "initial_manual_gates": initial_manual_gates,
            "initial_approval_command": approve_command,
            "review_gates": review_gates,
            "required_phases": required_phases,
            "automation_bias": "Minimize human stops after the required initial approval; use verifier, Santa dual-review, repair tasks, and final audit instead of repeated manual gating.",
        },
        "tasks": tasks,
    }


def _setup_review_task() -> Dict[str, Any]:
    return {
        "id": "G000_SETUP_REVIEW",
        "title": "Human review: approve Layer 0 files, skills, subagents, permissions, and verifier setup",
        "objective": (
            "Review PROJECT_SETUP.yml / SETUP_REVIEW.md and confirm all required files, Codex-native skills, "
            "Santa reviewers, allowed read/write roots, forbidden paths, and verifier commands are configured before task approval."
        ),
        "success_criteria": "A human inspected Layer 0 and approved with `python -m autopilot_nodekit approve-setup --workspace .`.",
        "status": "review_pending",
        "priority": 11000,
        "max_attempts": 1,
        "next_policy": {"manual_review": True, "approval_command": "python -m autopilot_nodekit approve-setup --workspace ."},
        "input_files": ["PROJECT_SETUP.yml", "SETUP_REVIEW.md", "AGENTS.md", ".agents/skills", ".codex/agents"],
        "expected_outputs": ["project_memory/rules.md", "automation/events.jsonl"],
        "done_when": ["Layer 0 files/skills/subagents/permissions are reviewed", "approval event exists in automation/events.jsonl"],
        "human_review_required": True,
        "memory": {"required_tags": ["setup", "codex", "skills", "permissions", "santa-review", "human-review"], "required_scopes": ["project", "decision", "tool"], "search_queries": ["Layer 0 setup files skills subagents permissions verifier"]},
    }


def _plan_review_task(*, depends_on: List[str]) -> Dict[str, Any]:
    return {
        "id": "H000_PLAN_REVIEW",
        "title": "Human review: approve generated task plan before execution",
        "objective": "Review the full task list, dependency graph, journal target, artifact naming, permission boundary, verifier policy, and per-task Santa review requirement.",
        "success_criteria": "A human inspected GOAL_CONTRACT.md, TASK_REVIEW.md, REQUIREMENTS_LOCK.md, and automation/manifest.live.md, then approved the plan.",
        "depends_on": depends_on,
        "status": "review_pending",
        "priority": 10000,
        "max_attempts": 1,
        "next_policy": {"manual_review": True, "approval_command": "python -m autopilot_nodekit approve-plan --workspace ."},
        "input_files": ["PROJECT_SETUP.yml", "GOAL_CONTRACT.yml", "automation/manifest.yml", "TASK_REVIEW.md"],
        "expected_outputs": ["TASK_REVIEW.md", "REQUIREMENTS_LOCK.md", "GOAL_CONTRACT.md", "automation/manifest.live.md"],
        "done_when": ["human reviewed the task count, graph, gates, permissions, verifier policy, and review policy", "approval event exists in automation/events.jsonl"],
        "human_review_required": True,
        "memory": {"required_task_ids": depends_on, "required_tags": ["plan", "contract", "journal", "figures", "human-review"], "required_scopes": ["project", "decision"], "search_queries": ["journal figure batch plan human approval task list"]},
    }


def _start_review_task(*, gate_mode: str) -> Dict[str, Any]:
    return {
        "id": "G000_START_REVIEW",
        "title": "Human review: approve project spec, Layer 0 setup, contract, and task manifest",
        "objective": (
            "Perform the single required startup review for fast/balanced loop modes: PROJECT_SPEC.yml, PROJECT_SETUP.yml, "
            "GOAL_CONTRACT.yml, TASK_REVIEW.md, REQUIREMENTS_LOCK.md, AGENTS.md, .agents/skills, .codex/agents, permission boundaries, verifier policy, and Santa review policy."
        ),
        "success_criteria": "A human approves the combined startup surface with `python -m autopilot_nodekit approve-start --workspace .`; after this, the system should avoid extra manual stops unless gate_mode=balanced pilot review is configured.",
        "status": "review_pending",
        "priority": 11000,
        "max_attempts": 1,
        "next_policy": {"manual_review": True, "approval_command": "python -m autopilot_nodekit approve-start --workspace ."},
        "input_files": ["PROJECT_SPEC.yml", "PROJECT_SPEC.md", "PROJECT_SETUP.yml", "GOAL_CONTRACT.yml", "TASK_REVIEW.md", "REQUIREMENTS_LOCK.md", "AGENTS.md", ".agents/skills", ".codex/agents"],
        "expected_outputs": ["project_memory/rules.md", "automation/events.jsonl"],
        "done_when": ["project spec is coherent", "task count and DAG are credible", "Layer 0 files and skills exist", "permissions and verifier are acceptable", "approval event exists in automation/events.jsonl"],
        "human_review_required": True,
        "memory": {"required_tags": ["startup", "project-spec", "setup", "plan", "codex", "permissions", "human-review"], "required_scopes": ["project", "decision", "tool"], "search_queries": [f"{gate_mode} startup approval project spec manifest permissions verifier"]},
    }


def _boundary_task(*, depends_on: List[str], output_dir: str) -> Dict[str, Any]:
    return {
        "id": "H010_BOUNDARY_PERMISSION_TEST",
        "title": "Boundary and permission test before artifact work",
        "objective": (
            "Run the smallest non-destructive test that proves Codex/NodeKit can read required inputs, write only "
            f"inside `{output_dir}`, access no forbidden locations, use the required skills/subagents, and run configured verifier commands."
        ),
        "success_criteria": "Boundary test passes; memory records allowed paths, forbidden paths, command permissions, sandbox mode, Santa review availability, and the exact verifier command to use.",
        "depends_on": depends_on,
        "priority": 9900,
        "max_attempts": 2,
        "verifier": {"command": "python -m autopilot_nodekit validate --workspace . --strict"},
        "input_files": ["PROJECT_SPEC.yml", "PROJECT_SETUP.yml", "GOAL_CONTRACT.yml", "automation/manifest.yml", "AGENTS.md", ".codex/config.toml", ".codex/agents"],
        "expected_outputs": ["project_memory/rules.md", "project_memory/decisions.md", "logs/raw/boundary_permission_test.md"],
        "done_when": ["approved read/write allowlist is recorded", "forbidden paths are documented", "strict validation passes", "sandbox mode is recorded", "Santa review path is recorded"],
        "forbidden": ["write data/raw", "edit automation/autopilot.sqlite directly", "write outside workspace"],
        "review_policy": santa_review_policy(),
        "memory": {"required_task_ids": depends_on, "required_tags": ["boundary", "permissions", "sandbox", "verifier", "santa-review"], "required_scopes": ["project", "tool", "decision"], "search_queries": ["permission boundary sandbox verifier output directory santa review"]},
    }


def _pilot_review_task(*, output_dir: str) -> Dict[str, Any]:
    return {
        "id": "H020_PILOT_REVIEW",
        "title": "Human review: approve Figure 001 and journal fit before bulk loop",
        "objective": "Inspect the completed first figure, journal formatting, naming conventions, caption assumptions, visual quality, verifier evidence, and Santa dual-review record before releasing the remaining figure batch.",
        "success_criteria": "A human confirms Figure 001 is acceptable as the template for the batch and approves with `python -m autopilot_nodekit approve-pilot --workspace .`.",
        "depends_on": ["F001_QC"],
        "status": "review_pending",
        "priority": 9700,
        "max_attempts": 1,
        "next_policy": {"manual_review": True, "approval_command": "python -m autopilot_nodekit approve-pilot --workspace ."},
        "input_files": [f"{output_dir}/F001.pdf", f"{output_dir}/F001.png", f"{output_dir}/F001.svg", "tasks/F001/evidence.md", "tasks/F001/journal_check.md", "runs/"],
        "expected_outputs": ["project_memory/human_feedback.md", "project_memory/rules.md"],
        "done_when": ["human inspected Figure 001 output quality", "journal fit and batch style decision are recorded", "pilot approval event exists in automation/events.jsonl"],
        "human_review_required": True,
        "memory": {"required_task_ids": ["F001_SPEC", "F001_RENDER", "F001_QC"], "required_tags": ["pilot", "journal", "figure", "quality", "human-review"], "required_scopes": ["decision", "task", "tool"], "search_queries": ["pilot figure journal approval template quality"]},
    }


def _final_audit_task(*, figure_count: int, qc_ids: List[str]) -> Dict[str, Any]:
    return {
        "id": "Z999_FINAL_AUDIT",
        "title": "Final audit: all journal figures verified",
        "objective": f"Check that all {figure_count} figures exist, match the journal target, have evidence-rich memory nodes, have valid Santa dual-review records for non-human tasks, and have no unresolved blocker tasks.",
        "success_criteria": "All figure QC tasks passed, graph validation passes, metrics exist, and final memory records the deliverable manifest.",
        "depends_on": qc_ids,
        "priority": 100,
        "max_attempts": 2,
        "verifier": {"command": "python -m autopilot_nodekit validate --workspace . --strict"},
        "input_files": ["PROJECT_SPEC.yml", "PROJECT_SETUP.yml", "automation/manifest.yml", "GOAL_CONTRACT.yml", "automation/manifest.live.md", "runs/"],
        "expected_outputs": ["automation/final_audit.md", "automation/metrics.json", "automation/metrics.md"],
        "done_when": ["all figure QC tasks passed", "strict validation passes", "metrics report exists", "no unresolved blocked tasks", "Santa review records exist for passed non-human tasks"],
        "review_policy": santa_review_policy(),
        "memory": {"required_task_ids": qc_ids[:60], "required_tags": ["figure", "qc", "final-audit", "santa-review"], "required_scopes": ["task", "decision", "bug"], "search_queries": ["final figure audit verifier missing output santa review"], "max_nodes_total": 80},
    }


def _figure_tasks(index: int, *, depends_on: List[str], journal: str, output_dir: str, tasks_per_figure: int, priority_base: int) -> List[Dict[str, Any]]:
    fid = figure_id(index)
    output_glob = f"{output_dir}/{fid}*"
    data_glob = f"data/{fid}*"
    task_dir = f"tasks/{fid}"
    script_path = f"scripts/figures/plot_{fid}.py"
    pdf_path = f"{output_dir}/{fid}.pdf"
    png_path = f"{output_dir}/{fid}.png"
    svg_path = f"{output_dir}/{fid}.svg"
    review_policy = santa_review_policy()
    tasks: List[Dict[str, Any]] = [
        {
            "id": f"{fid}_SPEC",
            "artifact_id": fid,
            "phase": "spec",
            "title": f"{fid}: define journal figure specification",
            "objective": f"Define the exact data inputs, panel layout, labels, scale bars/units, export formats, caption notes, and journal constraints for {fid} targeting {journal}.",
            "success_criteria": f"A reusable spec for {fid} is recorded in memory and names expected output files under `{output_dir}`.",
            "input_files": [data_glob, "GOAL_CONTRACT.yml", "PROJECT_SETUP.yml", "project_memory/rules.md"],
            "expected_outputs": [f"{task_dir}/spec.yml", f"{task_dir}/task_memory.md"],
            "done_when": ["input data/provenance is identified or blocked with evidence", "expected outputs and formats are listed", "journal size/unit/label requirements are stated", "Santa dual-review returns NICE/NICE"],
            "forbidden": ["invent missing data", "use placeholder labels without flagging"],
            "allowed_write_paths": [task_dir, "project_memory", "logs/raw", "runs", "memory/nodes"],
            "review_policy": review_policy,
            "depends_on": list(depends_on),
            "priority": priority_base,
            "max_attempts": 3,
            "memory": {"required_tags": ["figure", fid.lower(), "spec", "journal"], "required_scopes": ["project", "decision", "task", "tool"], "search_queries": [f"{fid} figure spec journal layout data inputs"]},
        },
        {
            "id": f"{fid}_RENDER",
            "artifact_id": fid,
            "phase": "render",
            "title": f"{fid}: render/export figure artifact",
            "objective": f"Create or update the {fid} figure artifact using the approved spec, writing outputs only under `{output_dir}`.",
            "success_criteria": f"At least one non-empty {fid} figure artifact exists under `{output_dir}` and the render command is recorded.",
            "input_files": [f"{task_dir}/spec.yml", data_glob],
            "expected_outputs": [pdf_path, png_path, svg_path, script_path, f"{task_dir}/evidence.md"],
            "done_when": ["script or command can reproduce the figure", "exported figure file exists and is non-empty", "raw command/output evidence is recorded", "Santa dual-review returns NICE/NICE"],
            "forbidden": ["write outside approved output/script/task directories", "mark placeholder output as complete"],
            "allowed_write_paths": [output_dir, script_path, task_dir, "logs/raw", "runs", "memory/nodes"],
            "review_policy": review_policy,
            "depends_on": [f"{fid}_SPEC"],
            "priority": priority_base - 1,
            "max_attempts": 4,
            "verifier": {"command": f"python -m autopilot_nodekit verify-artifact --workspace . --glob '{output_glob}' --min-bytes 512"},
            "memory": {"required_task_ids": [f"{fid}_SPEC"], "required_tags": ["figure", fid.lower(), "render", "export"], "required_scopes": ["tool", "task", "bug", "decision"], "search_queries": [f"{fid} render export figure artifact"]},
        },
        {
            "id": f"{fid}_QC",
            "artifact_id": fid,
            "phase": "qc",
            "title": f"{fid}: quality control and self-correction loop",
            "objective": f"Check {fid} against its spec, journal constraints, artifact existence, naming, visual consistency, and known errors. If problems are found, insert focused repair tasks using graph_patch rather than declaring success.",
            "success_criteria": f"{fid} passes artifact verification, QC memory records evidence, Santa dual-review approves, and unresolved issues are represented as graph_patch tasks.",
            "input_files": [pdf_path, png_path, svg_path, script_path, f"{task_dir}/spec.yml"],
            "expected_outputs": [f"{task_dir}/journal_check.md", f"{task_dir}/caption.md", f"{task_dir}/evidence.md"],
            "done_when": ["artifact verifier passes", "axis labels/units/caption/journal constraints are checked", "repair tasks exist for unresolved failures", "no unverified completion claim", "Santa dual-review returns NICE/NICE"],
            "forbidden": ["self-approve without verifier evidence", "hide QC failure in summary"],
            "allowed_write_paths": [task_dir, "project_memory", "logs/raw", "runs", "memory/nodes"],
            "review_policy": review_policy,
            "depends_on": [f"{fid}_RENDER"],
            "priority": priority_base - 2,
            "max_attempts": 4,
            "verifier": {"command": f"python -m autopilot_nodekit verify-artifact --workspace . --glob '{output_glob}' --min-bytes 512"},
            "memory": {"required_task_ids": [f"{fid}_SPEC", f"{fid}_RENDER"], "required_tags": ["figure", fid.lower(), "qc", "verification"], "required_scopes": ["task", "bug", "decision", "tool"], "search_queries": [f"{fid} figure QC verifier artifact journal"]},
        },
    ]
    if tasks_per_figure >= 4:
        compliance = {
            "id": f"{fid}_JOURNAL_CHECK",
            "artifact_id": fid,
            "phase": "journal_check",
            "title": f"{fid}: journal compliance check",
            "objective": f"Check {fid} against {journal} formatting and export constraints before QC.",
            "success_criteria": f"Journal compliance notes for {fid} are recorded; unresolved issues become repair tasks.",
            "input_files": [pdf_path, png_path, svg_path, f"{task_dir}/spec.yml", "GOAL_CONTRACT.yml"],
            "expected_outputs": [f"{task_dir}/journal_check.md"],
            "done_when": ["journal size/export/format assumptions are checked", "all deviations are recorded", "repair task exists for unresolved compliance issue", "Santa dual-review returns NICE/NICE"],
            "forbidden": ["ignore journal mismatch", "mark compliance passed without evidence"],
            "allowed_write_paths": [task_dir, "project_memory", "logs/raw", "runs", "memory/nodes"],
            "review_policy": review_policy,
            "depends_on": [f"{fid}_RENDER"],
            "priority": priority_base - 2,
            "max_attempts": 3,
            "memory": {"required_task_ids": [f"{fid}_SPEC", f"{fid}_RENDER"], "required_tags": ["figure", fid.lower(), "journal", "compliance"], "required_scopes": ["task", "decision", "bug"], "search_queries": [f"{fid} journal compliance figure format"]},
        }
        tasks.insert(2, compliance)
        tasks[-1]["depends_on"] = [f"{fid}_JOURNAL_CHECK"]
        tasks[-1]["priority"] = priority_base - 3
    elif tasks_per_figure == 2:
        tasks[1]["id"] = f"{fid}_QC"
        tasks[1]["phase"] = "render_qc"
        tasks[1]["title"] = f"{fid}: render, quality control, and self-correction"
        tasks[1]["objective"] = f"Render/export {fid}, verify the artifact, run Santa dual-review, and insert repair tasks if quality or journal constraints fail."
        tasks[1]["depends_on"] = [f"{fid}_SPEC"]
        tasks[1]["memory"]["required_task_ids"] = [f"{fid}_SPEC"]
        tasks = [tasks[0], tasks[1]]
    return tasks


def write_review_files(workspace: Path, manifest: Dict[str, Any]) -> None:
    paths = workspace_paths(workspace)
    ensure_memory_dirs(workspace)
    task_review = render_task_review(manifest)
    lock = render_requirements_lock(manifest)
    write_text(workspace / "TASK_REVIEW.md", task_review)
    write_text(workspace / "REQUIREMENTS_LOCK.md", lock)
    paths["automation"].mkdir(parents=True, exist_ok=True)
    write_text(paths["automation"] / "TASK_REVIEW.md", task_review)
    write_text(paths["automation"] / "REQUIREMENTS_LOCK.md", lock)


def write_figure_manifest(workspace: Path, manifest: Dict[str, Any]) -> None:
    paths = workspace_paths(workspace)
    paths["automation"].mkdir(parents=True, exist_ok=True)
    dump_yaml(paths["manifest"], manifest)
    project = manifest.get("project", {}) or {}
    if project.get("plan_type") == "journal_figures":
        figure_count = int(project.get("artifact_count") or 1)
        journal = str(project.get("journal") or "target journal")
        project_name = str(project.get("name") or "journal-figure-batch")
        output_dir = str(project.get("output_dir") or DEFAULT_OUTPUT_DIR)
        tasks_per_figure = int(project.get("tasks_per_artifact") or 3)
        gate_mode = str(project.get("gate_mode") or "strict")
        setup = build_figure_project_setup(
            figure_count=figure_count,
            journal=journal,
            project_name=project_name,
            output_dir=output_dir,
            gate_mode=gate_mode,
        )
        write_project_setup(workspace, setup)
        contract = build_figure_goal_contract(
            figure_count=figure_count,
            journal=journal,
            project_name=project_name,
            output_dir=output_dir,
            tasks_per_figure=tasks_per_figure,
            gate_mode=gate_mode,
        )
        write_goal_contract(workspace, contract)
    write_review_files(workspace, manifest)


def render_task_review(manifest: Dict[str, Any]) -> str:
    project = manifest.get("project", {}) or {}
    tasks = manifest.get("tasks", []) or []
    gates = project.get("review_gates", {}) or {}
    gate_mode = project.get("gate_mode", "strict")
    lines = [
        "# Task Review",
        "",
        "This file is for the required startup human review before Autopilot NodeKit runs worker tasks. In fast mode, this is the only manual stop before the loop; use verifier/Santa/repair/final audit for the rest.",
        "",
        "## Project",
        "",
        f"- name: `{project.get('name', '')}`",
        f"- goal: {project.get('goal', '')}",
        f"- plan_type: `{project.get('plan_type', '')}`",
        f"- artifact_count: `{project.get('artifact_count', '')}`",
        f"- actual_task_count: `{len(tasks)}`",
        f"- minimum_task_count: `{project.get('minimum_task_count', '')}`",
        f"- journal: `{project.get('journal', '')}`",
        f"- output_dir: `{project.get('output_dir', '')}`",
        f"- gate_mode: `{gate_mode}`",
        f"- task_scale: `{project.get('task_scale', '')}`",
        f"- pilot_policy: `{project.get('pilot_policy', '')}`",
        "",
        "## Human gates and loop policy",
        "",
    ]
    if gate_mode == "strict":
        lines += [
            f"0. Setup approval: `{gates.get('setup', 'G000_SETUP_REVIEW')}`.",
            f"1. Plan approval: `{gates.get('plan', 'H000_PLAN_REVIEW')}`.",
            f"2. Boundary test: `{gates.get('boundary_test', 'H010_BOUNDARY_PERMISSION_TEST')}` must pass.",
            f"3. Pilot review: `{gates.get('pilot', 'H020_PILOT_REVIEW')}` before F002+.",
            f"4. Final audit: `{gates.get('final_audit', 'Z999_FINAL_AUDIT')}`.",
        ]
    elif gate_mode == "balanced":
        lines += [
            f"0. Startup approval: `{gates.get('start', 'G000_START_REVIEW')}` covers project spec, Layer 0, contract, and manifest.",
            f"1. Boundary test: `{gates.get('boundary_test', 'H010_BOUNDARY_PERMISSION_TEST')}` must pass.",
            f"2. Pilot review: `{gates.get('pilot', 'H020_PILOT_REVIEW')}` before F002+.",
            f"3. Final audit: `{gates.get('final_audit', 'Z999_FINAL_AUDIT')}`.",
        ]
    else:
        lines += [
            f"0. Startup approval: `{gates.get('start', 'G000_START_REVIEW')}` covers project spec, Layer 0, contract, and manifest.",
            f"1. Boundary test: `{gates.get('boundary_test', 'H010_BOUNDARY_PERMISSION_TEST')}` must pass.",
            f"2. Figure 001 QC is the automatic pilot guard; F002+ depend on `{gates.get('automatic_pilot_guard', 'F001_QC')}`.",
            f"3. Final audit: `{gates.get('final_audit', 'Z999_FINAL_AUDIT')}`.",
        ]
    lines += [
        "",
        "## Santa review policy",
        "",
        "Every non-human task that reports `passed` must include `review.policy = santa_dual_review` and two independent reviewer verdicts: `reviewer_a.status = NICE` and `reviewer_b.status = NICE`. NodeKit will override a missing or failed review to `failed`.",
        "",
        "## Approval commands",
        "",
        "```bash",
    ]
    if gate_mode == "strict":
        lines += [
            "python -m autopilot_nodekit approve-setup --workspace . --summary 'Layer 0 setup reviewed and approved.'",
            "python -m autopilot_nodekit approve-plan --workspace . --summary 'Plan reviewed and approved.'",
            "python -m autopilot_nodekit approve-pilot --workspace . --summary 'Figure 001 reviewed and approved for batch loop.'",
        ]
    elif gate_mode == "balanced":
        lines += [
            "python -m autopilot_nodekit approve-start --workspace . --summary 'Project spec, Layer 0 setup, contract, task manifest, permissions, and loop mode reviewed.'",
            "python -m autopilot_nodekit approve-pilot --workspace . --summary 'Figure 001 reviewed and approved for batch loop.'",
        ]
    else:
        lines += ["python -m autopilot_nodekit approve-start --workspace . --summary 'Project spec, Layer 0 setup, contract, task manifest, permissions, and loop mode reviewed.'"]
    lines += [
        "```",
        "",
        "## Task list",
        "",
        "| # | task_id | status | depends_on | expected_outputs | review | title |",
        "|---:|---|---|---|---|---|---|",
    ]
    for idx, task in enumerate(tasks, 1):
        deps = ", ".join(task.get("depends_on", []) or [])
        outputs = ", ".join((task.get("expected_outputs") or [])[:3])
        review = "human" if task.get("human_review_required") else (task.get("review_policy", {}).get("method") if isinstance(task.get("review_policy"), dict) else "")
        lines.append(f"| {idx} | `{task.get('id')}` | `{task.get('status', 'auto')}` | {deps} | {outputs.replace('|', '/')} | {review} | {str(task.get('title', '')).replace('|', '/')} |")
    lines.append("")
    return "\n".join(lines)


def render_requirements_lock(manifest: Dict[str, Any]) -> str:
    project = manifest.get("project", {}) or {}
    count = int(project.get("artifact_count") or 0)
    min_count = int(project.get("minimum_task_count") or 0)
    gate_mode = project.get("gate_mode", "strict")
    gates = project.get("review_gates") or {}
    if gate_mode == "fast":
        gate_text = """- `G000_START_REVIEW` starts as `review_pending`; it is the only manual gate before the loop.
- `H010_BOUNDARY_PERMISSION_TEST` depends on `G000_START_REVIEW`.
- `F001_*` depends on the boundary test.
- Bulk figure tasks `F002+` depend on `F001_QC`, not a manual pilot gate.
- `Z999_FINAL_AUDIT` depends on all figure QC tasks."""
    elif gate_mode == "balanced":
        gate_text = """- `G000_START_REVIEW` starts as `review_pending`; it combines setup/contract/manifest review.
- `H010_BOUNDARY_PERMISSION_TEST` depends on `G000_START_REVIEW`.
- `H020_PILOT_REVIEW` starts as `review_pending` and depends on `F001_QC`.
- Bulk figure tasks `F002+` depend on `H020_PILOT_REVIEW`.
- `Z999_FINAL_AUDIT` depends on all figure QC tasks."""
    else:
        gate_text = """- `G000_SETUP_REVIEW` starts as `review_pending`; it is not claimable by workers.
- `H000_PLAN_REVIEW` starts as `review_pending`, depends on `G000_SETUP_REVIEW`, and is not claimable by workers.
- `H010_BOUNDARY_PERMISSION_TEST` depends on `H000_PLAN_REVIEW`.
- `H020_PILOT_REVIEW` starts as `review_pending` and depends on `F001_QC`.
- Bulk figure tasks `F002+` depend on `H020_PILOT_REVIEW`.
- `Z999_FINAL_AUDIT` depends on all figure QC tasks."""
    return f"""# Requirements Lock

These requirements are mandatory for this Autopilot NodeKit workspace.

## Gate mode

- gate_mode: `{gate_mode}`
- review_gates: `{gates}`

## Non-negotiable flow

0. Configure or review PROJECT_SPEC.yml and Layer 0 files/skills/subagents/permissions.
1. Approve only the minimal required human gate(s) for the selected gate mode.
2. Run a boundary/permission test before figure work.
3. Use Figure 001 as the pilot guard.
4. Run the bulk loop with verifier authority, Santa dual-review, repair tasks, self-iteration, and final verification.

## Scale requirement

- artifact_count: `{count}`
- minimum_task_count: `{min_count}`
- actual_task_count: `{len(manifest.get('tasks', []) or [])}`

For a large figure batch, the task graph must not collapse the work into a small vague task. With 100 figures and 3 tasks per figure, fast mode creates 303 tasks, balanced 304, strict 305.

## Runtime gates

{gate_text}

## Santa dual review

- Every non-human task must have `review_policy.method = santa_dual_review` and `review_policy.required = true`.
- Every passed worker result must include `review.policy = santa_dual_review` plus `reviewer_a.status = NICE` and `reviewer_b.status = NICE`.
- NodeKit will override a pass-like result to `failed` if either review is missing or NAUGHTY.

Do not bypass gates by manually editing SQLite. Use `approve-start`, `approve-setup`, `approve-plan`, `approve-pilot`, or `approve-task` so audit events are recorded.
"""
