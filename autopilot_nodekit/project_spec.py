from __future__ import annotations

import re
import shlex
from pathlib import Path
from typing import Any, Dict, List, Optional

from .util import dump_yaml, load_yaml, now_iso, read_text, write_text

SPEC_FILENAME = "PROJECT_SPEC.yml"
SPEC_REVIEW_FILENAME = "PROJECT_SPEC.md"
PROMPT_FILENAME = "PROJECT_PROMPT.md"

VALID_GATE_MODES = {"fast", "balanced", "strict"}
TASKS_PER_FIGURE_TO_SCALE = {2: "smoke", 3: "standard", 4: "prod"}


def project_spec_path(workspace: Path) -> Path:
    return workspace.resolve() / SPEC_FILENAME


def project_prompt_path(workspace: Path) -> Path:
    return workspace.resolve() / PROMPT_FILENAME


def load_project_spec(workspace: Path, default: Dict[str, Any] | None = None) -> Dict[str, Any]:
    path = project_spec_path(workspace)
    if not path.exists():
        return default or {}
    return load_yaml(path)


def write_project_spec(workspace: Path, spec: Dict[str, Any], *, prompt_text: str | None = None) -> None:
    workspace = workspace.resolve()
    dump_yaml(project_spec_path(workspace), spec)
    write_text(workspace / SPEC_REVIEW_FILENAME, render_project_spec_review(spec))
    if prompt_text is not None:
        write_text(project_prompt_path(workspace), prompt_text)


def infer_project_spec_from_prompt(
    prompt: str,
    *,
    figures: Optional[int] = None,
    journal: Optional[str] = None,
    project_name: Optional[str] = None,
    output_dir: str = "outputs/figures",
    data_dir: str = "data",
    script_dir: str = "scripts/figures",
    tasks_per_figure: int = 3,
    gate_mode: str = "fast",
) -> Dict[str, Any]:
    gate_mode = normalize_gate_mode(gate_mode)
    kind = detect_project_type(prompt)
    inferred_name = project_name or extract_project_name(prompt) or ("prompt-derived-figure-project" if kind == "journal_figures" else "prompt-derived-workflow-project")
    if kind == "journal_figures":
        inferred_figures = figures or extract_figure_count(prompt) or 1
        inferred_journal = journal or extract_journal(prompt) or "target journal"
        return build_figure_project_spec(
            project_name=inferred_name,
            figure_count=inferred_figures,
            journal=inferred_journal,
            output_dir=output_dir,
            data_dir=data_dir,
            script_dir=script_dir,
            tasks_per_figure=tasks_per_figure,
            gate_mode=gate_mode,
            source_prompt_excerpt=prompt.strip()[:4000],
        )
    artifact_count = figures or extract_artifact_count(prompt) or 4
    return build_workflow_project_spec(
        project_name=inferred_name,
        project_type=kind,
        artifact_count=artifact_count,
        output_dir=output_dir if output_dir != "outputs/figures" else "outputs/workflow",
        data_dir=data_dir,
        tasks_per_artifact=tasks_per_figure,
        gate_mode=gate_mode,
        source_prompt_excerpt=prompt.strip()[:4000],
    )


def build_figure_project_spec(
    *,
    project_name: str,
    figure_count: int,
    journal: str,
    output_dir: str = "outputs/figures",
    data_dir: str = "data",
    script_dir: str = "scripts/figures",
    tasks_per_figure: int = 3,
    gate_mode: str = "fast",
    source_prompt_excerpt: str = "",
) -> Dict[str, Any]:
    if figure_count < 1:
        raise ValueError("figure_count must be >= 1")
    if tasks_per_figure not in {2, 3, 4}:
        raise ValueError("tasks_per_figure must be 2, 3, or 4")
    gate_mode = normalize_gate_mode(gate_mode)
    gate_descriptions = {
        "fast": {
            "manual_gates": ["G000_START_REVIEW"],
            "meaning": "One human approval before execution; boundary test, first-figure pilot, bulk loop, Santa review, repair, and final audit are automated.",
        },
        "balanced": {
            "manual_gates": ["G000_START_REVIEW", "H020_PILOT_REVIEW"],
            "meaning": "One upfront approval and one first-figure approval before bulk release.",
        },
        "strict": {
            "manual_gates": ["G000_SETUP_REVIEW", "H000_PLAN_REVIEW", "H020_PILOT_REVIEW"],
            "meaning": "Separate Layer 0 setup approval, plan approval, and first-figure approval.",
        },
    }
    return {
        "version": 1,
        "source": {
            "kind": "prompt_derived_project_spec",
            "generator": "autopilot_nodekit.project_spec.infer_project_spec_from_prompt",
            "prompt_excerpt": source_prompt_excerpt,
        },
        "project": {
            "name": project_name,
            "type": "journal_figures",
            "artifact_kind": "figure",
            "artifact_count": figure_count,
            "journal": journal,
            "goal": f"Generate {figure_count} publication-ready figures for {journal}.",
        },
        "planning": {
            "tasks_per_figure": tasks_per_figure,
            "task_scale": TASKS_PER_FIGURE_TO_SCALE.get(tasks_per_figure, "standard"),
            "task_scale_meaning": "smoke=2 tasks/artifact; standard=3 tasks/artifact; prod=4 tasks/artifact with separate journal compliance check",
            "minimum_task_count": figure_count * tasks_per_figure + (5 if gate_mode == "strict" else 4 if gate_mode == "balanced" else 3),
            "gate_mode": gate_mode,
            "manual_gate_policy": gate_descriptions[gate_mode],
            "bulk_loop_policy": "After required gates pass, continue automatically through ready tasks; do not stop for non-critical approvals.",
            "startup_question_policy": "If gate_mode, task_scale, artifact_count, target_journal, or generated output files are unclear, ask the user before starting the graph.",
            "pilot_policy": "fast mode uses F001_QC as an automatic pilot guard; balanced/strict modes require H020_PILOT_REVIEW before F002+.",
        },
        "inputs": {
            "data_dir": data_dir,
            "expected_patterns": [
                f"{data_dir}/F001*",
                f"{data_dir}/F002* ... {data_dir}/F{figure_count:03d}* or a recorded source-location decision",
            ],
            "missing_input_policy": "Block with evidence or insert a focused source-discovery/repair task; never fabricate data.",
        },
        "outputs": {
            "figure_dir": output_dir,
            "script_dir": script_dir,
            "per_figure": [
                f"{output_dir}/<figure_id>.pdf",
                f"{output_dir}/<figure_id>.png",
                f"{output_dir}/<figure_id>.svg",
                f"{script_dir}/plot_<figure_id>.py",
                "tasks/<figure_id>/spec.yml",
                "tasks/<figure_id>/caption.md",
                "tasks/<figure_id>/journal_check.md",
                "tasks/<figure_id>/evidence.md",
            ],
        },
        "definition_of_done": [
            "Each figure has identified source data or an approved missing-input exception.",
            "Each figure has a reproducible script or build command.",
            "PDF/PNG/SVG outputs exist and are non-empty.",
            "Caption, provenance, journal-format notes, and QC evidence are recorded.",
            "Verifier passes before the task is complete.",
            "Santa dual-review returns NICE/NICE for every non-human pass.",
            "Final audit passes with no unresolved blockers.",
        ],
        "forbidden": [
            "Do not fabricate data, labels, captions, or provenance.",
            "Do not mark placeholder figures as complete.",
            "Do not edit raw data in place.",
            "Do not bypass review_pending gates or edit automation/autopilot.sqlite directly.",
            "Do not mark a task complete from LLM self-report without verifier evidence.",
        ],
        "permissions": {
            "sandbox": "workspace-write",
            "approval_policy": "on-request",
            "read_allow": [".", data_dir, "project_memory", "automation", "memory", "runs", "tasks"],
            "write_allow": [output_dir, script_dir, "tasks", "project_memory", "logs/raw", "runs", "memory/nodes", "automation"],
            "write_deny": ["data/raw", ".git", "automation/autopilot.sqlite", "PROJECT_SPEC.yml", "GOAL_CONTRACT.yml", "PROJECT_SETUP.yml"],
        },
        "codex_native": {
            "required_files": ["AGENTS.md", ".agents/skills", ".codex/config.toml", ".codex/agents", ".codex/hooks.json"],
            "goal_mode": True,
            "skills": ["autopilot-project-spec", "autopilot-review-gated-figure-loop", "autopilot-santa-review"],
            "subagents": ["autopilot-santa-reviewer-a", "autopilot-santa-reviewer-b", "autopilot-checker", "autopilot-explorer"],
        },
        "verification": {
            "authoritative": True,
            "default_commands": [
                "python -m autopilot_nodekit validate --workspace . --strict",
                f"python -m autopilot_nodekit verify-artifact --workspace . --glob '{output_dir}/F001*' --min-bytes 512",
            ],
        },
        "background": {
            "backend_policy": "Detect tmux/nohup/setsid/powershell/foreground and choose the best available backend for this OS.",
            "timeout_policy": "Background worker loops have no wall-clock timeout by default; use --max-cycles 0 for unlimited cycles.",
        },
        "repair_policy": {
            "max_iterations_per_task": 4,
            "required_failure_fields": ["failure_reason", "responsible_files", "patch_summary", "verifier_output"],
            "insert_repair_task_on_qc_failure": True,
            "escalate_repeated_failure_after": 2,
        },
    }


def normalize_gate_mode(mode: str | None) -> str:
    mode = (mode or "fast").strip().lower()
    if mode not in VALID_GATE_MODES:
        raise ValueError(f"gate_mode must be one of {sorted(VALID_GATE_MODES)}, got {mode!r}")
    return mode



def detect_project_type(prompt: str) -> str:
    lower = prompt.lower()
    explicit_no_figure_template = bool(re.search(r"不要用期刊图模板|不要.*figure template|not.*figure template|非.*期刊图", lower))
    # Figure projects are common and should not be stolen by incidental words like
    # "workflow" or substrings such as "dify" inside "modify". But an explicit
    # anti-template instruction must win.
    if not explicit_no_figure_template and (extract_figure_count(prompt) or re.search(r"publication[- ]ready\s*(figure|figures|plot|plots)|期刊图|论文图", lower)):
        return "journal_figures"
    if re.search(r"\bragflow\b|\brag[- ]?based\b|\blocal[- ]?llm\b|knowledge base|知识库|数据库|\bdify\b|\bopenwebui\b", lower):
        return "rag_local_llm"
    if re.search(r"\bsevennet\b|\b7net\b|\bvasp\b|\bdft\b|\bslurm\b|\bmlip\b|fine[- ]?tuning|fine tuning|势能|机器学习势", lower):
        return "materials_dft_sevennet"
    if re.search(r"\bmatlantis\b|\bnotebook\b|\base\b|\bneb\b|\bmd\b|moo3|mos2|材料计算|工作流", lower):
        return "matlantis_workflow"
    return "science_workflow"


def extract_artifact_count(prompt: str) -> Optional[int]:
    # Prefer explicit artifact/count wording for generic workflows; otherwise use 4 stages.
    patterns = [
        r"(?:artifact_count|artifacts|workflow stages|stages|任务阶段|阶段数)\s*[:：=]?\s*(\d{1,4})",
        r"(\d{1,4})\s*(?:个|项)?\s*(?:artifact|artifacts|workflow stages|stages|阶段)",
    ]
    for pattern in patterns:
        m = re.search(pattern, prompt, flags=re.IGNORECASE)
        if m:
            try:
                n = int(m.group(1))
                if n > 0:
                    return n
            except Exception:
                pass
    return None


def build_workflow_project_spec(
    *,
    project_name: str,
    project_type: str,
    artifact_count: int = 4,
    output_dir: str = "outputs/workflow",
    data_dir: str = "data",
    tasks_per_artifact: int = 3,
    gate_mode: str = "balanced",
    source_prompt_excerpt: str = "",
) -> Dict[str, Any]:
    if artifact_count < 1:
        artifact_count = 4
    if tasks_per_artifact not in {2, 3, 4}:
        raise ValueError("tasks_per_artifact must be 2, 3, or 4")
    gate_mode = normalize_gate_mode(gate_mode)
    stage_names = default_stage_names(project_type, artifact_count)
    gate_extra = 5 if gate_mode == "strict" else 4 if gate_mode == "balanced" else 3
    return {
        "version": 1,
        "source": {
            "kind": "prompt_derived_project_spec",
            "generator": "autopilot_nodekit.project_spec.infer_project_spec_from_prompt",
            "prompt_excerpt": source_prompt_excerpt,
        },
        "project": {
            "name": project_name,
            "type": project_type,
            "artifact_kind": "workflow_stage",
            "artifact_count": artifact_count,
            "goal": f"Build a verifier-backed {project_type} workflow package with auditable evidence and repair loops.",
        },
        "planning": {
            "tasks_per_artifact": tasks_per_artifact,
            "tasks_per_figure": tasks_per_artifact,
            "task_scale": TASKS_PER_FIGURE_TO_SCALE.get(tasks_per_artifact, "standard"),
            "minimum_task_count": artifact_count * tasks_per_artifact + gate_extra,
            "gate_mode": gate_mode,
            "manual_gate_policy": {
                "manual_gates": ["G000_START_REVIEW"] + (["H020_PILOT_REVIEW"] if gate_mode == "balanced" else []),
                "meaning": "Workflow/science project: approve startup, run boundary/bootstrap test, optionally review first stage, then keep background loop running.",
            },
            "stage_names": stage_names,
            "demo_quarantine": "Exclude demo/sample/template/test-fixture content unless explicitly approved by the user.",
        },
        "inputs": {"data_dir": data_dir, "missing_input_policy": "Block or insert source-discovery task; never fabricate data or labels."},
        "outputs": {"output_dir": output_dir, "workflow_stage_dirs": [f"tasks/F{i:03d}" for i in range(1, artifact_count + 1)]},
        "definition_of_done": [
            "Every workflow stage has input_files, expected_outputs, done_when, and verifier or documented blocking reason.",
            "No demo/template artifact is treated as a real deliverable.",
            "Background worker bootstrap checks pass before business tasks.",
            "Verifier evidence and Santa NICE/NICE exist for each non-human pass.",
            "Final audit passes with no unresolved blockers.",
        ],
        "forbidden": [
            "Do not use figure/demo defaults unless the project is explicitly a figure batch.",
            "Do not fabricate scientific data, DFT labels, notebook results, or RAG answers.",
            "Do not launch duplicate background workers.",
            "Do not submit external jobs unless the task contract permits it and required gates passed.",
        ],
        "permissions": {
            "sandbox": "workspace-write",
            "approval_policy": "on-request",
            "read_allow": [".", data_dir, "project_memory", "automation", "memory", "runs", "tasks"],
            "write_allow": [output_dir, "tasks", "project_memory", "logs/raw", "runs", "memory/nodes", "automation"],
            "write_deny": [".git", "automation/autopilot.sqlite"],
        },
        "codex_native": {"required_files": ["AGENTS.md", ".agents/skills", ".codex/config.toml", ".codex/agents", ".codex/hooks.json", ".nodekit"]},
        "verification": {"authoritative": True, "default_commands": ["python -m autopilot_nodekit background-doctor --workspace . --json", "python -m autopilot_nodekit validate --workspace . --strict"]},
        "repair_policy": {"max_iterations_per_task": 4, "use_resolve_by_repair": True, "stale_recovery": "Use recover-stale for abandoned running tasks."},
    }


def default_stage_names(project_type: str, artifact_count: int) -> List[str]:
    presets = {
        "matlantis_workflow": [
            "literature and structure source registry plus physical contract",
            "structure builders, validators, and structure_validation_report framework",
            "main Matlantis notebook, helper modules, and CALCULATION_MATRIX",
            "dry-run smoke tests, verifier, full-run plan, and final audit package",
        ],
        "materials_dft_sevennet": [
            "capability audit for SevenNet/VASP/Slurm/runtime",
            "original large-model audit and local-environment coverage plan",
            "reduced-model candidate generation and validation",
            "DFT input matrix, SevenNet dataset conversion, and fine-tuning plan",
        ],
        "rag_local_llm": [
            "RAGFlow deployment and local service health",
            "API capability and authentication probing",
            "dataset design, source allowlist, and ingestion route plan",
            "retrieval QA evaluation, repair plan, and final audit package",
        ],
    }
    names = list(presets.get(project_type, [])) or [
        "source registry and contract",
        "builders and validators",
        "main workflow implementation",
        "smoke tests and final audit plan",
    ]
    while len(names) < artifact_count:
        names.append(f"additional workflow stage {len(names)+1}")
    return names[:artifact_count]

def extract_figure_count(prompt: str) -> Optional[int]:
    patterns = [
        r"(\d{1,5})\s*(?:个|張|张)?\s*(?:期刊|论文|paper|journal)?\s*(?:图|圖|figure|figures|figs|plots)",
        r"(?:图|圖|figure|figures|figs|plots)\s*[:：]?\s*(\d{1,5})",
        r"(\d{1,5})\s*(?:publication[- ]ready\s*)?(?:figures|plots)",
    ]
    for pattern in patterns:
        m = re.search(pattern, prompt, flags=re.IGNORECASE)
        if m:
            try:
                n = int(m.group(1))
                if n > 0:
                    return n
            except Exception:
                pass
    return None


def extract_journal(prompt: str) -> Optional[str]:
    patterns = [
        r"(?:journal|target journal|期刊)\s*[:：]\s*([^\n,，;；。]+)",
        r"(?:for|targeting|投稿到|投给|目标期刊)\s+((?:Nature|Science|Cell|PNAS|Advanced Materials|Nano Letters|ACS Nano|Nature Communications)[^\n,，;；。]*)",
    ]
    for pattern in patterns:
        m = re.search(pattern, prompt, flags=re.IGNORECASE)
        if m:
            value = m.group(1).strip().strip("'\"")
            if value:
                return value
    for name in ["Nature Communications", "Advanced Materials", "Nano Letters", "ACS Nano", "Nature", "Science", "Cell", "PNAS"]:
        if re.search(r"\b" + re.escape(name) + r"\b", prompt, flags=re.IGNORECASE):
            return name
    return None


def extract_project_name(prompt: str) -> Optional[str]:
    for line in prompt.splitlines():
        s = line.strip().strip("# ").strip()
        if not s:
            continue
        if len(s) <= 80 and not re.search(r"\d+\s*(?:个|張|张)?\s*(?:图|figure|figures|plots)", s, re.IGNORECASE):
            return re.sub(r"[^A-Za-z0-9_.\-\u4e00-\u9fff]+", "-", s).strip("-")[:80] or None
    return None


def spec_to_figure_plan_kwargs(spec: Dict[str, Any]) -> Dict[str, Any]:
    project = spec.get("project", {}) or {}
    planning = spec.get("planning", {}) or {}
    outputs = spec.get("outputs", {}) or {}
    return {
        "figure_count": int(project.get("artifact_count") or 1),
        "project_name": str(project.get("name") or "prompt-derived-figure-project"),
        "journal": str(project.get("journal") or "target journal"),
        "output_dir": str(outputs.get("figure_dir") or "outputs/figures"),
        "tasks_per_figure": int(planning.get("tasks_per_figure") or 3),
        "gate_mode": normalize_gate_mode(planning.get("gate_mode") or "fast"),
        "project_spec": spec,
    }


def spec_to_workflow_plan_kwargs(spec: Dict[str, Any]) -> Dict[str, Any]:
    project = spec.get("project", {}) or {}
    planning = spec.get("planning", {}) or {}
    outputs = spec.get("outputs", {}) or {}
    return {
        "artifact_count": int(project.get("artifact_count") or 4),
        "project_name": str(project.get("name") or "prompt-derived-workflow-project"),
        "project_type": str(project.get("type") or "science_workflow"),
        "goal": str(project.get("goal") or "Build a verifier-backed workflow package."),
        "output_dir": str(outputs.get("output_dir") or outputs.get("figure_dir") or "outputs/workflow"),
        "tasks_per_artifact": int(planning.get("tasks_per_artifact") or planning.get("tasks_per_figure") or 3),
        "gate_mode": normalize_gate_mode(planning.get("gate_mode") or "balanced"),
        "stage_names": list(planning.get("stage_names") or []),
        "project_spec": spec,
    }


def render_project_spec_review(spec: Dict[str, Any]) -> str:
    project = spec.get("project", {}) or {}
    planning = spec.get("planning", {}) or {}
    lines: List[str] = [
        "# Project Spec Review",
        "",
        "This spec is the human-readable project interface. NodeKit converts it into PROJECT_SETUP.yml, GOAL_CONTRACT.yml, automation/manifest.yml, and per-task Codex prompts.",
        "",
        "## Project",
        "",
        f"- name: `{project.get('name', '')}`",
        f"- type: `{project.get('type', '')}`",
        f"- artifact_count: `{project.get('artifact_count', '')}`",
        f"- journal: `{project.get('journal', '')}`",
        f"- goal: {project.get('goal', '')}",
        "",
        "## Loop mode",
        "",
        f"- gate_mode: `{planning.get('gate_mode', '')}`",
        f"- manual_gates: `{', '.join((planning.get('manual_gate_policy') or {}).get('manual_gates', []) or [])}`",
        f"- policy: {(planning.get('manual_gate_policy') or {}).get('meaning', '')}",
        f"- tasks_per_artifact: `{planning.get('tasks_per_artifact', planning.get('tasks_per_figure', ''))}`",
        f"- task_scale: `{planning.get('task_scale', '')}`",
        f"- minimum_task_count: `{planning.get('minimum_task_count', '')}`",
        "",
        "## Definition of Done",
        "",
    ]
    lines += [f"- {item}" for item in spec.get("definition_of_done", []) or []]
    lines += ["", "## Forbidden", ""]
    lines += [f"- {item}" for item in spec.get("forbidden", []) or []]
    lines += [
        "",
        "## Strong commands",
        "",
        "```bash",
        "python -m autopilot_nodekit start-from-spec --workspace . --spec PROJECT_SPEC.yml --force-codex-native",
        "python -m autopilot_nodekit background-doctor --workspace .",
        "python -m autopilot_nodekit launch-background --workspace . --worker-id codex-worker --max-cycles 0",
        "```",
        "",
        "`next-command` is for diagnosis and supervision, not the normal task-by-task button.",
        "",
    ]
    return "\n".join(lines)



def prepare_codex_spec_draft(
    workspace: Path,
    prompt_file: Path,
    *,
    gate_mode: str = "fast",
    output_path: Path | str = SPEC_FILENAME,
) -> Dict[str, Any]:
    """Prepare a one-command Codex handoff that lets Codex draft PROJECT_SPEC.yml.

    This does not start the task graph. It creates a replayable run directory with
    the source project prompt, the native `/goal` instruction, and a shell script
    that launches Codex in workspace-write/on-request mode.
    """
    workspace = workspace.resolve()
    gate_mode = normalize_gate_mode(gate_mode)
    prompt_file = prompt_file if prompt_file.is_absolute() else workspace / prompt_file
    prompt_text = prompt_file.read_text(encoding="utf-8")
    run_id = "spec-draft-" + now_iso().replace(":", "").replace("-", "").replace("Z", "")
    run_dir = workspace / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    copied_prompt = run_dir / "project_prompt.md"
    copied_prompt.write_text(prompt_text, encoding="utf-8")

    goal = build_codex_spec_goal(copied_prompt, output_path)
    goal += (
        f" Use planning.gate_mode={gate_mode}. "
        "Prefer the smallest safe human-gate set that still preserves no-fabrication, verifier authority, Santa review, repair-loop, and final-audit guarantees."
    )
    goal_path = run_dir / "codex_spec_goal.txt"
    goal_path.write_text(goal + "\n", encoding="utf-8")

    script = run_dir / "open_codex_spec.sh"
    script.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        f"cd {shlex.quote(str(workspace))}\n"
        f"codex exec --sandbox workspace-write --ask-for-approval on-request --skip-git-repo-check \"$(cat {shlex.quote(str(goal_path))})\" < {shlex.quote(str(copied_prompt))}\n"
        "echo\n"
        "echo 'Next commands:'\n"
        "echo 'python -m autopilot_nodekit project-spec-review --workspace .'\n"
        "echo 'python -m autopilot_nodekit start-from-spec --workspace . --spec PROJECT_SPEC.yml --force-codex-native'\n",
        encoding="utf-8",
    )
    script.chmod(0o755)
    return {
        "run_id": run_id,
        "run_dir": str(run_dir),
        "prompt_copy": str(copied_prompt),
        "goal_path": str(goal_path),
        "script": str(script),
        "command": f"bash {script}",
        "next_after_codex": "python -m autopilot_nodekit start-from-spec --workspace . --spec PROJECT_SPEC.yml --force-codex-native",
    }

def build_codex_spec_goal(prompt_path: Path | str = PROMPT_FILENAME, output_path: Path | str = SPEC_FILENAME) -> str:
    return (
        f"/goal Read `{prompt_path}` and write a complete `{output_path}` for Autopilot NodeKit. "
        "The spec must include project.name, project.type (journal_figures only when truly a figure batch; otherwise science_workflow/materials_dft_sevennet/matlantis_workflow/rag_local_llm), project.artifact_count, planning.tasks_per_artifact, planning.gate_mode, inputs, outputs, definition_of_done, forbidden, permissions, codex_native, verification, and repair_policy. "
        "If gate_mode or task_scale is not specified, write explicit questions in PROJECT_SPEC.md instead of silently guessing. "
        "Gate modes are fast/balanced/strict. Task scales are smoke/standard/prod. "
        "Do not start execution; only create or refine the project specification and explain any missing assumptions in PROJECT_SPEC.md."
    )
