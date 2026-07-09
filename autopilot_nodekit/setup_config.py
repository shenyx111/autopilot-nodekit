from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from .util import dump_yaml, load_yaml, write_text, workspace_paths

SETUP_FILENAME = "PROJECT_SETUP.yml"
SETUP_REVIEW_FILENAME = "SETUP_REVIEW.md"

REQUIRED_SETUP_TOP_LEVEL = [
    "project",
    "inputs",
    "outputs",
    "codex_native_files",
    "skills",
    "subagents",
    "permissions",
    "verifier",
    "human_gate",
]


def setup_path(workspace: Path) -> Path:
    return workspace.resolve() / SETUP_FILENAME


def setup_review_path(workspace: Path) -> Path:
    return workspace.resolve() / SETUP_REVIEW_FILENAME


def load_project_setup(workspace: Path, default: Dict[str, Any] | None = None) -> Dict[str, Any]:
    path = setup_path(workspace)
    if not path.exists():
        return default or {}
    return load_yaml(path)


def build_figure_project_setup(
    *,
    figure_count: int,
    journal: str,
    project_name: str = "journal-figure-batch",
    output_dir: str = "outputs/figures",
    data_dir: str = "data",
    script_dir: str = "scripts/figures",
    gate_mode: str = "strict",
) -> Dict[str, Any]:
    gate_mode = (gate_mode or "strict").strip().lower()
    startup_gate_id = "G000_START_REVIEW" if gate_mode in {"fast", "balanced"} else "G000_SETUP_REVIEW"
    startup_gate_command = "python -m autopilot_nodekit approve-start --workspace ." if startup_gate_id == "G000_START_REVIEW" else "python -m autopilot_nodekit approve-setup --workspace ."
    return {
        "version": 1,
        "project": {
            "name": project_name,
            "kind": "journal_figure_batch",
            "artifact_count": figure_count,
            "journal": journal,
            "purpose": "Layer 0 setup: enumerate files, directories, skills, subagents, permissions, verification commands, and the selected gate mode before the task plan is approved.",
            "gate_mode": gate_mode,
        },
        "inputs": {
            "required_roots": [data_dir],
            "expected_patterns": [
                f"{data_dir}/F001*",
                f"{data_dir}/F002* ... {data_dir}/F{figure_count:03d}* or an approved source-location exception",
                "journal requirements file or project_memory/rules.md entry",
            ],
            "missing_input_policy": "Block the task with evidence; never fabricate data or treat placeholder figures as complete.",
        },
        "outputs": {
            "required_roots": [output_dir, script_dir, "tasks", "project_memory", "logs/raw", "runs", "memory/nodes", "automation"],
            "per_figure_required": [
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
        "codex_native_files": [
            "AGENTS.md",
            "LOOP_STATE.md",
            "PLANS.md",
            ".codex/config.toml",
            ".codex/hooks.json",
            ".codex/hooks/autopilot_stop_render.py",
            ".codex/agents/autopilot-checker.toml",
            ".codex/agents/autopilot-explorer.toml",
            ".codex/agents/autopilot-santa-reviewer-a.toml",
            ".codex/agents/autopilot-santa-reviewer-b.toml",
        ],
        "skills": [
            ".agents/skills/autopilot-nodekit-loop-contract/SKILL.md",
            ".agents/skills/autopilot-nodekit-codex-goal/SKILL.md",
            ".agents/skills/autopilot-nodekit-worker-result/SKILL.md",
            ".agents/skills/autopilot-nodekit-graph-curator/SKILL.md",
            ".agents/skills/autopilot-nodekit-memory-curator/SKILL.md",
            ".agents/skills/autopilot-review-gated-figure-loop/SKILL.md",
            ".agents/skills/autopilot-santa-review/SKILL.md",
        ],
        "subagents": {
            "required_for_pass": True,
            "method": "santa_dual_review",
            "reviewers": ["autopilot-santa-reviewer-a", "autopilot-santa-reviewer-b"],
            "rule": "Every non-human task that reports passed must include two independent NICE reviews in worker_result.json.",
        },
        "permissions": {
            "sandbox": "workspace-write",
            "approval_policy": "on-request",
            "read_allow": [".", data_dir, "project_memory", "automation", "memory", "runs", "tasks"],
            "write_allow": [output_dir, script_dir, "tasks", "project_memory", "logs/raw", "runs", "memory/nodes", "automation"],
            "write_deny": ["data/raw", ".git", "automation/autopilot.sqlite", "GOAL_CONTRACT.yml", "PROJECT_SETUP.yml"],
        },
        "verifier": {
            "required_for_pass": True,
            "commands": [
                "python -m autopilot_nodekit validate --workspace . --strict",
                f"python -m autopilot_nodekit verify-artifact --workspace . --glob '{output_dir}/F001*' --min-bytes 512",
            ],
        },
        "human_gate": {
            "id": startup_gate_id,
            "status": "review_pending",
            "gate_mode": gate_mode,
            "approval_command": startup_gate_command,
            "review_files": ["PROJECT_SETUP.yml", "SETUP_REVIEW.md", "AGENTS.md", ".agents/skills", ".codex/agents"],
        },
    }


def write_project_setup(workspace: Path, setup: Dict[str, Any]) -> None:
    workspace = workspace.resolve()
    dump_yaml(setup_path(workspace), setup)
    write_text(setup_review_path(workspace), render_setup_review(setup))


def render_setup_review(setup: Dict[str, Any]) -> str:
    project = setup.get("project", {}) or {}
    lines: List[str] = [
        "# Layer 0 Setup Review",
        "",
        "This is the first human gate. Do not approve the task manifest until the setup surface is credible.",
        "",
        "## Project",
        "",
        f"- name: `{project.get('name', '')}`",
        f"- kind: `{project.get('kind', '')}`",
        f"- artifact_count: `{project.get('artifact_count', '')}`",
        f"- journal: `{project.get('journal', '')}`",
        "",
    ]
    for key in ["inputs", "outputs", "codex_native_files", "skills", "subagents", "permissions", "verifier", "human_gate"]:
        lines += [f"## {key}", "", _render_value(setup.get(key)), ""]
    gate = setup.get("human_gate", {}) or {}
    approval_command = gate.get("approval_command") or "python -m autopilot_nodekit approve-setup --workspace ."
    summary = "Project spec, Layer 0 setup, contract, task manifest, permissions, and loop mode reviewed." if gate.get("id") == "G000_START_REVIEW" else "Layer 0 files, skills, subagents, permissions, and verifier reviewed."
    lines += [
        "## Human approval command",
        "",
        "Only run this after checking file paths, allowed writes, Codex skills, subagents, and verifier policy:",
        "",
        "```bash",
        f"{approval_command} --summary '{summary}'",
        "```",
        "",
    ]
    return "\n".join(lines)


def validate_project_setup(workspace: Path, setup: Dict[str, Any] | None = None) -> Dict[str, List[Dict[str, Any]]]:
    errors: List[Dict[str, Any]] = []
    warnings: List[Dict[str, Any]] = []
    setup = setup if setup is not None else load_project_setup(workspace)
    if not setup:
        errors.append({"type": "missing_project_setup", "path": SETUP_FILENAME})
        return {"errors": errors, "warnings": warnings}
    for key in REQUIRED_SETUP_TOP_LEVEL:
        if _is_empty(setup.get(key)):
            errors.append({"type": "setup_missing_required_field", "field": key})
    required_files = [*(setup.get("codex_native_files") or []), *(setup.get("skills") or [])]
    for rel in required_files:
        path = workspace / str(rel)
        if not path.exists():
            errors.append({"type": "setup_required_file_missing", "path": str(rel)})
    subagents = setup.get("subagents", {}) or {}
    if subagents.get("required_for_pass") and len(subagents.get("reviewers") or []) < 2:
        errors.append({"type": "setup_requires_two_santa_reviewers"})
    gate = setup.get("human_gate", {}) or {}
    if gate.get("id") not in {"G000_SETUP_REVIEW", "G000_START_REVIEW"}:
        errors.append({"type": "setup_gate_id_must_be_known_start_gate", "actual": gate.get("id")})
    return {"errors": errors, "warnings": warnings}


def _render_value(value: Any) -> str:
    import json

    if isinstance(value, list):
        return "\n".join(f"- {item}" for item in value) or "(empty)"
    if isinstance(value, dict):
        lines = []
        for k, v in value.items():
            if isinstance(v, (list, dict)):
                lines.append(f"- `{k}`: {json.dumps(v, ensure_ascii=False)}")
            else:
                lines.append(f"- `{k}`: {v}")
        return "\n".join(lines) or "(empty)"
    return str(value or "(empty)")


def _is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, tuple, set, dict)):
        return len(value) == 0
    return False
