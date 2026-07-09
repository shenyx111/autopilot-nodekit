from __future__ import annotations

import json
from pathlib import Path

from autopilot_nodekit.cli import main
from autopilot_nodekit.db import AutoDB
from autopilot_nodekit.manifest import import_manifest
from autopilot_nodekit.recovery import resolve_by_repair
from autopilot_nodekit.util import dump_yaml, load_yaml, workspace_paths
from autopilot_nodekit.workflow import next_command


def test_smart_start_non_figure_prompt_uses_workflow_template(tmp_path: Path) -> None:
    prompt = tmp_path / "PROJECT_PROMPT.md"
    prompt.write_text(
        "基于 autopilot-nodekit 建立 Matlantis notebook workflow。gate mode: balanced。task scale: prod。artifact_count: 4。不要用期刊图模板。",
        encoding="utf-8",
    )
    code = main(["smart-start", "--workspace", str(tmp_path), "--prompt-file", str(prompt), "--force-codex-native"])
    assert code == 0
    spec = load_yaml(tmp_path / "PROJECT_SPEC.yml")
    manifest = load_yaml(tmp_path / "automation" / "manifest.yml")
    assert spec["project"]["type"] == "matlantis_workflow"
    assert manifest["project"]["plan_type"] == "matlantis_workflow"
    assert manifest["project"]["artifact_kind"] == "workflow_stage"
    titles = "\n".join(t["title"] for t in manifest["tasks"])
    assert "journal compliance" not in titles.lower()
    assert "structure_validation_report" in titles


def test_ensure_default_config_installs_worker_wrapper(tmp_path: Path) -> None:
    prompt = tmp_path / "PROJECT_PROMPT.md"
    prompt.write_text("100 figures, Nature, gate mode: fast, task scale: smoke", encoding="utf-8")
    code = main(["smart-start", "--workspace", str(tmp_path), "--prompt-file", str(prompt), "--force-codex-native"])
    assert code == 0
    config = load_yaml(tmp_path / "automation" / "config.yml")
    assert config["worker"]["agent"] == "codex-cli"
    assert config["worker"]["command"]
    assert (tmp_path / ".nodekit" / "codex_worker.sh").exists()
    assert "/bin/sh" not in (tmp_path / ".codex" / "hooks.json").read_text(encoding="utf-8")


def test_next_command_does_not_finish_background_run_without_result(tmp_path: Path) -> None:
    paths = workspace_paths(tmp_path)
    paths["automation"].mkdir(parents=True)
    manifest = {"tasks": [{"id": "T001", "title": "bg", "objective": "run", "success_criteria": "ok"}]}
    dump_yaml(paths["manifest"], manifest)
    dump_yaml(paths["config"], {"worker": {"agent": "codex-cli", "command": "echo ok"}})
    db = AutoDB(paths["db"])
    db.init_schema()
    try:
        import_manifest(db, paths["manifest"])
        claim = db.claim_ready_task("codex-worker", lease_seconds=0)
        assert claim is not None
        task, run_id = claim
        db.update_run_paths(run_id, agent="codex-cli", result_json_path=str(paths["runs"] / run_id / "worker_result.json"))
        info = next_command(tmp_path, db)
        assert info["phase"] == "background_task_running_monitor_only"
        assert "recover-stale" in info["why"]
    finally:
        db.close()


def test_lease_seconds_zero_means_no_expiry(tmp_path: Path) -> None:
    paths = workspace_paths(tmp_path)
    paths["automation"].mkdir(parents=True)
    manifest = {"tasks": [{"id": "T001", "title": "long", "objective": "run", "success_criteria": "ok"}]}
    dump_yaml(paths["manifest"], manifest)
    dump_yaml(paths["config"], {"worker": {"agent": "codex-cli", "command": "echo ok"}})
    db = AutoDB(paths["db"])
    db.init_schema()
    try:
        import_manifest(db, paths["manifest"])
        claim = db.claim_ready_task("codex-worker", lease_seconds=0)
        assert claim is not None
        task, _ = claim
        assert task["status"] == "running"
        assert task["lease_until"] is None
        db.refresh_ready_tasks()
        assert db.get_task("T001")["status"] == "running"
        assert db.claim_ready_task("second-worker", lease_seconds=0) is None
    finally:
        db.close()


def test_resolve_by_repair_rewires_downstream_and_supersedes_failed_parent(tmp_path: Path) -> None:
    paths = workspace_paths(tmp_path)
    paths["automation"].mkdir(parents=True)
    manifest = {
        "tasks": [
            {"id": "T001", "title": "failed", "objective": "x", "success_criteria": "x"},
            {"id": "T001_REPAIR_01", "parent_id": "T001", "title": "repair", "objective": "x", "success_criteria": "x"},
            {"id": "T002", "title": "downstream", "objective": "x", "success_criteria": "x", "depends_on": ["T001"]},
        ]
    }
    dump_yaml(paths["manifest"], manifest)
    dump_yaml(paths["config"], {"worker": {"agent": "shell", "command": ""}})
    db = AutoDB(paths["db"])
    db.init_schema()
    try:
        import_manifest(db, paths["manifest"])
        db.complete_task_run("T001", db.claim_ready_task("w", 0)[1], "failed", "failed", exit_code=1)
        # Manually mark repair passed for focused unit test.
        db.conn.execute("UPDATE tasks SET status='passed' WHERE id='T001_REPAIR_01'")
        report = resolve_by_repair(db, "T001", "T001_REPAIR_01")
        assert report["rewired_edges"]
        assert db.get_task("T001")["status"] == "superseded"
        edges = db.list_edges(from_task="T002", edge_type="depends_on")
        assert [e["to_task"] for e in edges] == ["T001_REPAIR_01"]
    finally:
        db.close()


def test_codex_native_generated_text_has_current_public_guidance(tmp_path: Path) -> None:
    from autopilot_nodekit.codex_native import install_codex_native_files

    install_codex_native_files(tmp_path, force=True)
    generated = [tmp_path / "AGENTS.md", *sorted((tmp_path / ".agents" / "skills").glob("**/SKILL.md"))]
    text = "\n".join(path.read_text(encoding="utf-8") for path in generated)
    assert "v0." + "7" not in text
    assert "v0." + "8" not in text
    assert "verifier-" + "authoritative " + "DO" + "NE" not in text
    assert "launch-background --workspace . --worker-id codex-worker --max-cycles 0" in text
