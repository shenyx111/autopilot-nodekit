from __future__ import annotations

from pathlib import Path

from autopilot_nodekit.cli import main
from autopilot_nodekit.smart_start import analyze_start_prompt, TASK_SCALE_TO_TASKS_PER_FIGURE
from autopilot_nodekit.background import detect_background_backends
from autopilot_nodekit.util import load_yaml


def test_smart_start_requires_gate_mode_and_task_scale_when_prompt_omits_them(tmp_path: Path) -> None:
    prompt = tmp_path / "PROJECT_PROMPT.md"
    prompt.write_text("我要做100个期刊图，目标期刊 Nature。每张图必须有源数据、脚本和PDF。", encoding="utf-8")
    code = main(["smart-start", "--workspace", str(tmp_path), "--prompt-file", str(prompt), "--force-codex-native"])
    assert code == 2
    questions = (tmp_path / "START_QUESTIONS.md").read_text(encoding="utf-8")
    assert "gate_mode" in questions
    assert "task_scale" in questions
    assert not (tmp_path / "automation" / "manifest.yml").exists()


def test_smart_start_with_confirmed_answers_generates_prod_task_count(tmp_path: Path) -> None:
    prompt = tmp_path / "PROJECT_PROMPT.md"
    prompt.write_text("我要做100个期刊图，目标期刊 Nature。每张图必须有源数据、脚本、PDF/PNG/SVG、caption 和 QC。", encoding="utf-8")
    answers = tmp_path / "START_ANSWERS.yml"
    answers.write_text(
        "confirmed: true\n"
        "gate_mode: fast\n"
        "task_scale: prod\n"
        "artifact_count: 100\n"
        "target_journal: Nature\n"
        "data_dir: data\n"
        "output_dir: outputs/figures\n",
        encoding="utf-8",
    )
    code = main(["smart-start", "--workspace", str(tmp_path), "--prompt-file", str(prompt), "--answers", str(answers), "--force-codex-native"])
    assert code == 0
    manifest = load_yaml(tmp_path / "automation" / "manifest.yml")
    assert manifest["project"]["task_scale"] == "prod"
    assert manifest["project"]["tasks_per_artifact"] == 4
    assert len(manifest["tasks"]) == 403
    assert (tmp_path / "PROJECT_SPEC.yml").exists()
    assert (tmp_path / "AGENTS.md").read_text(encoding="utf-8").find("Smart-start trigger rule") != -1


def test_background_doctor_always_has_foreground_fallback() -> None:
    info = detect_background_backends()
    assert info["selected"]
    assert any(b["name"] == "foreground" and b["available"] for b in info["backends"])


def test_task_scale_mapping_is_three_tier() -> None:
    assert TASK_SCALE_TO_TASKS_PER_FIGURE == {"smoke": 2, "standard": 3, "prod": 4}
