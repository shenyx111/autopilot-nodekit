from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .project_spec import (
    extract_figure_count,
    extract_journal,
    extract_project_name,
    infer_project_spec_from_prompt,
    normalize_gate_mode,
    detect_project_type,
    extract_artifact_count,
)
from .util import dump_yaml, load_yaml, read_text, write_text

VALID_TASK_SCALES = {"smoke", "standard", "prod"}
TASK_SCALE_TO_TASKS_PER_FIGURE = {"smoke": 2, "standard": 3, "prod": 4}
TASK_SCALE_DESCRIPTIONS = {
    "smoke": "Minimal-per-artifact graph for fast verification: spec + render/QC per artifact. For 100 figures this is about 203 tasks in fast mode.",
    "standard": "Default production loop: spec + render + QC per artifact. For 100 figures this is about 303 tasks in fast mode.",
    "prod": "Strongest artifact contract: spec + render + journal check + QC per artifact. For 100 figures this is about 403 tasks in fast mode.",
}

REQUIRED_START_FIELDS = ["gate_mode", "task_scale", "artifact_count", "target_journal"]


@dataclass
class StartAnalysis:
    resolved: Dict[str, Any]
    missing: List[Dict[str, Any]]
    warnings: List[Dict[str, Any]]

    @property
    def ready(self) -> bool:
        return not self.missing


def normalize_task_scale(value: str | None) -> str:
    s = (value or "").strip().lower()
    aliases = {
        "production": "prod",
        "productive": "prod",
        "full": "prod",
        "release": "prod",
        "标准": "standard",
        "默认": "standard",
        "平衡": "standard",
        "生产": "prod",
        "正式": "prod",
        "冒烟": "smoke",
        "测试": "smoke",
    }
    s = aliases.get(s, s)
    if s not in VALID_TASK_SCALES:
        raise ValueError(f"task_scale must be one of {sorted(VALID_TASK_SCALES)}, got {value!r}")
    return s


def extract_gate_mode(prompt: str) -> Optional[str]:
    lower = prompt.lower()
    if re.search(r"\bstrict\b|严格|强审核|高审核", lower):
        return "strict"
    if re.search(r"\bbalanced\b|balance|平衡|pilot review|第一个.*审核|首个.*审核", lower):
        return "balanced"
    if re.search(r"\bfast\b|快速|少审核|不要.*停|尽量.*自动|减少.*审核", lower):
        return "fast"
    return None


def extract_task_scale(prompt: str) -> Optional[str]:
    # Only accept explicit task-scale wording. Generic words such as
    # "figure production" must not silently select prod.
    patterns = [
        (r"(?:task[_ -]?scale|任务规模|任务档位|scale)\s*[:：=]?\s*(prod|production|正式|生产|全量)", "prod"),
        (r"(?:task[_ -]?scale|任务规模|任务档位|scale)\s*[:：=]?\s*(standard|标准|默认|常规)", "standard"),
        (r"(?:task[_ -]?scale|任务规模|任务档位|scale)\s*[:：=]?\s*(smoke|冒烟|小试|测试跑|最小验证)", "smoke"),
        (r"(?:使用|用|选择)\s*(prod|production|正式|生产)\s*(?:task[_ -]?scale|任务规模|任务档位|档)", "prod"),
        (r"(?:使用|用|选择)\s*(standard|标准|默认|常规)\s*(?:task[_ -]?scale|任务规模|任务档位|档)", "standard"),
        (r"(?:使用|用|选择)\s*(smoke|冒烟|小试|测试跑)\s*(?:task[_ -]?scale|任务规模|任务档位|档)", "smoke"),
    ]
    for pattern, value in patterns:
        if re.search(pattern, prompt, flags=re.IGNORECASE):
            return value
    return None


def extract_data_dir(prompt: str) -> Optional[str]:
    patterns = [
        r"(?:data|数据|source data|输入数据)\s*(?:dir|directory|目录|在|=|:|：)?\s*[`'\"]?([A-Za-z0-9_./\\-]+)[`'\"]?",
        r"(?:输入|数据)\s*(?:在|位于)\s*([A-Za-z0-9_./\\-]+)",
    ]
    for pattern in patterns:
        m = re.search(pattern, prompt, flags=re.IGNORECASE)
        if m:
            value = m.group(1).strip().rstrip("。.,，;；")
            if value and not value.lower() in {"dir", "directory"}:
                return value
    return None


def extract_output_dir(prompt: str) -> Optional[str]:
    patterns = [
        r"(?:output|outputs|输出|figure_dir|图输出)\s*(?:dir|directory|目录|到|=|:|：)?\s*[`'\"]?([A-Za-z0-9_./\\-]+)[`'\"]?",
        r"(?:保存到|写到|输出到)\s*([A-Za-z0-9_./\\-]+)",
    ]
    for pattern in patterns:
        m = re.search(pattern, prompt, flags=re.IGNORECASE)
        if m:
            value = m.group(1).strip().rstrip("。.,，;；")
            if value and not value.lower() in {"dir", "directory"}:
                return value
    return None


def prompt_mentions_deliverables(prompt: str) -> bool:
    return bool(re.search(r"pdf|png|svg|caption|脚本|script|qc|evidence|检查|deliverable|输出", prompt, flags=re.IGNORECASE))


def analyze_start_prompt(
    prompt: str,
    *,
    figures: Optional[int] = None,
    journal: Optional[str] = None,
    gate_mode: Optional[str] = None,
    task_scale: Optional[str] = None,
    project_name: Optional[str] = None,
    output_dir: Optional[str] = None,
    data_dir: Optional[str] = None,
    answers: Optional[Dict[str, Any]] = None,
) -> StartAnalysis:
    answers = answers or {}
    resolved: Dict[str, Any] = {}
    warnings: List[Dict[str, Any]] = []

    resolved["project_type"] = first_present(answers.get("project_type"), detect_project_type(prompt))
    is_figure_project = resolved["project_type"] == "journal_figures"
    resolved["artifact_count"] = first_present(figures, answers.get("artifact_count"), extract_figure_count(prompt) if is_figure_project else extract_artifact_count(prompt))
    resolved["target_journal"] = first_present(journal, answers.get("target_journal"), answers.get("journal"), extract_journal(prompt))
    resolved["gate_mode"] = first_present(gate_mode, answers.get("gate_mode"), extract_gate_mode(prompt))
    resolved["task_scale"] = first_present(task_scale, answers.get("task_scale"), extract_task_scale(prompt))
    resolved["project_name"] = first_present(project_name, answers.get("project_name"), extract_project_name(prompt), "prompt-derived-figure-project" if is_figure_project else "prompt-derived-workflow-project")
    resolved["data_dir"] = first_present(data_dir, answers.get("data_dir"), extract_data_dir(prompt), "data")
    resolved["output_dir"] = first_present(output_dir, answers.get("output_dir"), extract_output_dir(prompt), "outputs/figures" if is_figure_project else "outputs/workflow")
    resolved["deliverables"] = answers.get("deliverables") or ["pdf", "png", "svg", "plotting_script", "caption", "qc_report"]

    missing: List[Dict[str, Any]] = []
    if not resolved["gate_mode"]:
        missing.append(
            question(
                "gate_mode",
                "选择审核强度：fast / balanced / strict。prompt 没有明确说明时必须问用户。",
                ["fast", "balanced", "strict"],
                "balanced",
            )
        )
    else:
        resolved["gate_mode"] = normalize_gate_mode(str(resolved["gate_mode"]))

    if not resolved["task_scale"]:
        missing.append(
            question(
                "task_scale",
                "选择任务规模：smoke / standard / prod。prompt 没有明确说明时必须问用户。",
                ["smoke", "standard", "prod"],
                "standard",
            )
        )
    else:
        resolved["task_scale"] = normalize_task_scale(str(resolved["task_scale"]))
        resolved["tasks_per_figure"] = TASK_SCALE_TO_TASKS_PER_FIGURE[resolved["task_scale"]]

    if not resolved["artifact_count"]:
        missing.append(question("artifact_count", "要生成/处理多少个主要产物？例如 100 个期刊图。", None, 1))
    else:
        try:
            resolved["artifact_count"] = int(resolved["artifact_count"])
        except Exception:
            missing.append(question("artifact_count", "artifact_count 不是有效整数，请给出明确数量。", None, 1))

    if is_figure_project and not resolved["target_journal"]:
        missing.append(question("target_journal", "目标期刊/格式规范是什么？例如 Nature / Science / ACS Nano。", None, "target journal"))
    elif not is_figure_project and not resolved["target_journal"]:
        resolved["target_journal"] = "not_applicable"

    if not prompt_mentions_deliverables(prompt) and not answers.get("deliverables_confirmed"):
        warnings.append(
            {
                "field": "deliverables",
                "message": "prompt 没有明确输出文件类型；将默认生成 PDF/PNG/SVG、plotting script、caption、QC report。需要不同输出时请在 START_ANSWERS.yml 里改。",
            }
        )

    if resolved.get("artifact_count") and resolved.get("task_scale"):
        gate_extra = 5 if resolved.get("gate_mode") == "strict" else 4 if resolved.get("gate_mode") == "balanced" else 3
        resolved["minimum_task_count"] = int(resolved["artifact_count"]) * TASK_SCALE_TO_TASKS_PER_FIGURE[resolved["task_scale"]] + gate_extra

    return StartAnalysis(resolved=resolved, missing=missing, warnings=warnings)


def first_present(*values: Any) -> Any:
    for value in values:
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        return value
    return None


def question(field: str, message: str, choices: Optional[List[str]], default: Any) -> Dict[str, Any]:
    out = {"field": field, "question": message, "default": default}
    if choices:
        out["choices"] = choices
    return out


def load_start_answers(path: Path | None) -> Dict[str, Any]:
    if not path:
        return {}
    if not path.exists():
        return {}
    return load_yaml(path)


def write_start_questions(workspace: Path, analysis: StartAnalysis) -> None:
    write_text(workspace / "START_QUESTIONS.md", render_start_questions(analysis))
    template: Dict[str, Any] = {
        "confirmed": False,
        "gate_mode": "",
        "task_scale": "",
        "artifact_count": None,
        "project_type": analysis.resolved.get("project_type", "science_workflow"),
        "target_journal": "",
        "data_dir": analysis.resolved.get("data_dir", "data"),
        "output_dir": analysis.resolved.get("output_dir", "outputs/workflow"),
        "deliverables": analysis.resolved.get("deliverables") or ["pdf", "png", "svg", "plotting_script", "caption", "qc_report"],
        "deliverables_confirmed": False,
    }
    for item in analysis.missing:
        template[item["field"]] = item.get("default")
    dump_yaml(workspace / "START_ANSWERS.yml.template", template)


def render_start_questions(analysis: StartAnalysis) -> str:
    lines = [
        "# Start Questions",
        "",
        "Autopilot NodeKit detected an ambiguous startup prompt. The graph has not been started yet.",
        "Answer these settings before generating PROJECT_SPEC.yml and automation/manifest.yml.",
        "",
        "## Missing required settings",
        "",
    ]
    if not analysis.missing:
        lines.append("None.")
    else:
        for idx, item in enumerate(analysis.missing, 1):
            lines.append(f"{idx}. `{item['field']}` — {item['question']}")
            if item.get("choices"):
                lines.append(f"   - choices: {', '.join(item['choices'])}")
            lines.append(f"   - default suggestion: `{item.get('default')}`")
    lines += ["", "## Warnings", ""]
    if not analysis.warnings:
        lines.append("None.")
    else:
        for item in analysis.warnings:
            lines.append(f"- `{item['field']}` — {item['message']}")
    lines += [
        "",
        "## Task scale meanings",
        "",
    ]
    for scale in ["smoke", "standard", "prod"]:
        lines.append(f"- `{scale}`: {TASK_SCALE_DESCRIPTIONS[scale]}")
    lines += [
        "",
        "## Next command after filling answers",
        "",
        "```bash",
        "cp START_ANSWERS.yml.template START_ANSWERS.yml",
        "# edit START_ANSWERS.yml, set confirmed: true",
        "python -m autopilot_nodekit smart-start --workspace . --prompt-file PROJECT_PROMPT.md --answers START_ANSWERS.yml --force-codex-native",
        "```",
        "",
    ]
    return "\n".join(lines)


def build_spec_from_resolved(prompt: str, resolved: Dict[str, Any]) -> Dict[str, Any]:
    task_scale = normalize_task_scale(str(resolved["task_scale"]))
    tasks_per_figure = TASK_SCALE_TO_TASKS_PER_FIGURE[task_scale]
    spec = infer_project_spec_from_prompt(
        prompt,
        figures=int(resolved["artifact_count"]),
        journal=str(resolved["target_journal"]),
        project_name=str(resolved.get("project_name") or "prompt-derived-figure-project"),
        output_dir=str(resolved.get("output_dir") or "outputs/figures"),
        data_dir=str(resolved.get("data_dir") or "data"),
        tasks_per_figure=tasks_per_figure,
        gate_mode=str(resolved["gate_mode"]),
    )
    spec.setdefault("planning", {})["task_scale"] = task_scale
    if spec.get("project", {}).get("type") == "journal_figures":
        spec["planning"]["task_scale_description"] = TASK_SCALE_DESCRIPTIONS[task_scale]
        missing_note = "gate_mode/task_scale/artifact_count/journal"
    else:
        spec["planning"]["task_scale_description"] = "smoke=2 tasks/artifact; standard=3 tasks/artifact; prod=4 tasks/artifact with a separate validation step"
        missing_note = "gate_mode/task_scale/artifact_count/project_type"
    spec["planning"]["startup_policy"] = f"Always generate PROJECT_PROMPT.md, PROJECT_SPEC.yml, Goal Contract, Task Manifest, and start questions before execution. Missing {missing_note} must be answered before start."
    spec.setdefault("outputs", {})["deliverables"] = resolved.get("deliverables") or spec.get("outputs", {}).get("per_figure", [])
    spec.setdefault("background", {})["timeout_policy"] = "No background worker timeout is imposed by NodeKit defaults; worker-loop can run with --max-cycles 0 for unlimited cycles."
    return spec


def smart_start_prompt_text(user_prompt: str) -> str:
    return (
        "基于 autopilot-nodekit 包里的固定流程，完成以下任务。"
        "先生成 PROJECT_PROMPT.md / PROJECT_SPEC.yml / GOAL_CONTRACT.yml / automation/manifest.yml。"
        "如果 gate_mode、task_scale、artifact_count、target_journal 或生成文件类型不明确，先问用户并等待回答，不要直接开始任务。\n\n"
        "以下是我的项目 prompt：\n" + user_prompt.strip() + "\n"
    )
