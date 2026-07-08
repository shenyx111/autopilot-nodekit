from __future__ import annotations

import json
import textwrap
from pathlib import Path

from autopilot_nodekit.db import AutoDB
from autopilot_nodekit.manifest import import_manifest
from autopilot_nodekit.runner import run_once
from autopilot_nodekit.util import dump_yaml, load_yaml, workspace_paths


def init_workspace(tmp_path: Path, manifest: dict, config: dict) -> AutoDB:
    paths = workspace_paths(tmp_path)
    paths["automation"].mkdir(parents=True, exist_ok=True)
    paths["runs"].mkdir(parents=True, exist_ok=True)
    paths["memory_nodes"].mkdir(parents=True, exist_ok=True)
    dump_yaml(paths["manifest"], manifest)
    dump_yaml(paths["config"], config)
    db = AutoDB(paths["db"])
    db.init_schema()
    import_manifest(db, paths["manifest"])
    return db


def base_config(command: str) -> dict:
    return {
        "worker": {"agent": "shell-test", "command": command, "timeout_seconds": 60},
        "verifier": {"command": "", "timeout_seconds": 60},
        "memory": {"inject_full_nodes": False, "max_nodes_total": 24, "include_raw_artifact_paths": True},
    }


def write_worker(tmp_path: Path, body: str) -> str:
    path = tmp_path / "worker.py"
    path.write_text(textwrap.dedent(body), encoding="utf-8")
    return f"python {path}"


def test_verifier_failure_overrides_worker_passed(tmp_path: Path) -> None:
    command = write_worker(
        tmp_path,
        """
        import json, os, pathlib
        run_dir = pathlib.Path(os.environ['AUTOPILOT_RUN_DIR'])
        (run_dir / 'worker_result.json').write_text(json.dumps({
            'status': 'passed',
            'summary': 'worker self-reported pass',
            'details': 'verifier should override this',
            'memory_nodes': []
        }), encoding='utf-8')
        """,
    )
    manifest = {
        "tasks": [
            {
                "id": "T001",
                "title": "Verifier override",
                "objective": "Worker lies; verifier fails.",
                "success_criteria": "Task must be failed because verifier fails.",
                "verifier": {"command": "python -c \"import sys; sys.exit(1)\"", "timeout_seconds": 30},
            }
        ]
    }
    db = init_workspace(tmp_path, manifest, base_config(command))
    try:
        run_id = run_once(tmp_path, db, "w1")
        assert run_id
        task = db.get_task("T001")
        assert task["status"] == "failed"
        normalized = json.loads((tmp_path / "runs" / run_id / "worker_result.normalized.json").read_text(encoding="utf-8"))
        assert normalized["status"] == "failed"
        assert "verifier failed" in normalized["summary"]
        assert (tmp_path / "runs" / run_id / "verifier.log").exists()
    finally:
        db.close()


def test_bad_worker_result_json_does_not_leave_task_running(tmp_path: Path) -> None:
    command = write_worker(
        tmp_path,
        """
        import os, pathlib
        run_dir = pathlib.Path(os.environ['AUTOPILOT_RUN_DIR'])
        (run_dir / 'worker_result.json').write_text('{bad json', encoding='utf-8')
        """,
    )
    manifest = {
        "tasks": [
            {
                "id": "T001",
                "title": "Bad result",
                "objective": "Write invalid JSON.",
                "success_criteria": "Control plane must mark failed and preserve payload.",
            }
        ]
    }
    db = init_workspace(tmp_path, manifest, base_config(command))
    try:
        run_id = run_once(tmp_path, db, "w1")
        assert run_id
        task = db.get_task("T001")
        assert task["status"] == "failed"
        run_dir = tmp_path / "runs" / run_id
        assert (run_dir / "worker_result.invalid.json").exists()
        result = json.loads((run_dir / "worker_result.json").read_text(encoding="utf-8"))
        assert result["status"] == "failed"
        assert "Invalid worker_result.json" in result["summary"]
    finally:
        db.close()



def test_santa_dual_review_required_before_task_passes(tmp_path: Path) -> None:
    command = write_worker(
        tmp_path,
        """
        import json, os, pathlib
        run_dir = pathlib.Path(os.environ['AUTOPILOT_RUN_DIR'])
        (run_dir / 'worker_result.json').write_text(json.dumps({
            'status': 'passed',
            'summary': 'worker says done without reviewers',
            'details': 'control plane must reject this',
            'memory_nodes': []
        }), encoding='utf-8')
        """,
    )
    manifest = {
        "tasks": [
            {
                "id": "T_SANTA",
                "title": "Santa review gate",
                "objective": "Verify dual-review is authoritative.",
                "success_criteria": "Task cannot pass without NICE/NICE review evidence.",
                "input_files": ["data/input.csv"],
                "expected_outputs": ["figures/output.pdf"],
                "done_when": ["output exists", "reviewers both return NICE"],
                "review_policy": {
                    "method": "santa_dual_review",
                    "required": True,
                    "reviewers": ["autopilot-santa-reviewer-a", "autopilot-santa-reviewer-b"],
                },
            }
        ]
    }
    db = init_workspace(tmp_path, manifest, base_config(command))
    try:
        run_id = run_once(tmp_path, db, "w1")
        assert run_id
        task = db.get_task("T_SANTA")
        assert task["status"] == "failed"
        normalized = json.loads((tmp_path / "runs" / run_id / "worker_result.normalized.json").read_text(encoding="utf-8"))
        assert normalized["status"] == "failed"
        assert "Santa dual-review failed" in normalized["summary"]
    finally:
        db.close()

def test_after_attempt_bridge_task_after_failed_parent_becomes_ready(tmp_path: Path) -> None:
    bridge_result = {
        "status": "failed",
        "summary": "Need bridge",
        "details": "Insert diagnostic bridge after this failed attempt.",
        "memory_nodes": [
            {
                "title": "Setup unknown",
                "scope": "bug",
                "tags": ["setup", "entrypoint", "blocked", "verification"],
                "content": "Setup command unknown.",
                "confidence": 0.9,
            }
        ],
        "graph_patch": {
            "operations": [
                {
                    "op": "add_task",
                    "task": {
                        "id": "T001.1",
                        "parent_id": "T001",
                        "title": "Diagnose setup",
                        "objective": "Find setup command.",
                        "success_criteria": "Memory node records setup command.",
                        "after_attempt": ["T001"],
                        "priority": 110,
                        "memory": {"required_task_ids": ["T001"], "required_tags": ["setup"]},
                    },
                },
                {"op": "update_task", "id": "T002", "fields": {"status": "blocked", "result_summary": "Blocked until T001.1"}},
            ]
        },
    }
    worker_payload = json.dumps(bridge_result)
    command = write_worker(
        tmp_path,
        f"""
        import os, pathlib
        run_dir = pathlib.Path(os.environ['AUTOPILOT_RUN_DIR'])
        (run_dir / 'worker_result.json').write_text({worker_payload!r}, encoding='utf-8')
        """,
    )
    manifest = {
        "tasks": [
            {"id": "T001", "title": "Preflight", "objective": "Fail and insert bridge.", "success_criteria": "Bridge inserted.", "priority": 100},
            {"id": "T002", "title": "Implementation", "objective": "Blocked by preflight.", "success_criteria": "Not run yet.", "depends_on": ["T001"], "priority": 90},
        ]
    }
    db = init_workspace(tmp_path, manifest, base_config(command))
    try:
        run_once(tmp_path, db, "w1")
        assert db.get_task("T001")["status"] == "failed"
        assert db.get_task("T001.1")["status"] == "ready"
        assert db.get_task("T002")["status"] == "blocked"
        memory_plan_ids = [m["task_id"] for m in db.list_memory_for_task_ids(["T001"], limit=10)]
        assert "T001" in memory_plan_ids
    finally:
        db.close()


def test_events_jsonl_is_written(tmp_path: Path) -> None:
    command = write_worker(
        tmp_path,
        """
        import json, os, pathlib
        run_dir = pathlib.Path(os.environ['AUTOPILOT_RUN_DIR'])
        (run_dir / 'worker_result.json').write_text(json.dumps({'status': 'passed', 'summary': 'ok', 'details': 'ok'}), encoding='utf-8')
        """,
    )
    manifest = {"tasks": [{"id": "T001", "title": "Event audit", "objective": "Run", "success_criteria": "Pass"}]}
    db = init_workspace(tmp_path, manifest, base_config(command))
    try:
        run_once(tmp_path, db, "w1")
    finally:
        db.close()
    events_path = tmp_path / "automation" / "events.jsonl"
    assert events_path.exists()
    lines = events_path.read_text(encoding="utf-8").splitlines()
    assert any('"task_completed"' in line for line in lines)


def test_task_level_verifier_takes_precedence_over_global_verifier(tmp_path: Path) -> None:
    command = write_worker(
        tmp_path,
        """
        import json, os, pathlib
        run_dir = pathlib.Path(os.environ['AUTOPILOT_RUN_DIR'])
        (run_dir / 'worker_result.json').write_text(json.dumps({
            'status': 'passed',
            'summary': 'task verifier wins',
            'details': 'global verifier would fail but task verifier passes',
            'memory_nodes': []
        }), encoding='utf-8')
        """,
    )
    config = base_config(command)
    config["verifier"] = {"command": "python -c \"import sys; sys.exit(9)\"", "timeout_seconds": 30}
    manifest = {
        "tasks": [
            {
                "id": "T001",
                "title": "Task verifier precedence",
                "objective": "Task verifier should override config verifier.",
                "success_criteria": "Task passes because its own verifier passes.",
                "verifier": {"command": "python -c \"import sys; sys.exit(0)\"", "timeout_seconds": 30},
            }
        ]
    }
    db = init_workspace(tmp_path, manifest, config)
    try:
        run_id = run_once(tmp_path, db, "w1")
        assert run_id
        assert db.get_task("T001")["status"] == "passed"
        control = json.loads((tmp_path / "runs" / run_id / "control_result.json").read_text(encoding="utf-8"))
        assert control["verifier_exit_code"] == 0
        assert control["verifier_source"] == "task"
        run_row = db.list_runs("T001")[0]
        assert run_row["verifier_path"].endswith("verifier.log")
    finally:
        db.close()


def test_manifest_reimport_replaces_declared_edge_list(tmp_path: Path) -> None:
    manifest = {
        "tasks": [
            {"id": "T001", "title": "One", "objective": "one", "success_criteria": "one"},
            {"id": "T002", "title": "Two", "objective": "two", "success_criteria": "two", "depends_on": ["T001"]},
            {"id": "T003", "title": "Three", "objective": "three", "success_criteria": "three"},
        ]
    }
    db = init_workspace(tmp_path, manifest, base_config("python -c 'print(0)'"))
    try:
        assert [(e["from_task"], e["to_task"], e["edge_type"]) for e in db.list_edges("T002", "depends_on")] == [("T002", "T001", "depends_on")]
        manifest["tasks"][1]["depends_on"] = ["T003"]
        dump_yaml(tmp_path / "automation" / "manifest.yml", manifest)
        import_manifest(db, tmp_path / "automation" / "manifest.yml")
        assert [(e["from_task"], e["to_task"], e["edge_type"]) for e in db.list_edges("T002", "depends_on")] == [("T002", "T003", "depends_on")]
    finally:
        db.close()


def test_codex_goal_generation_uses_task_verifier_and_stays_compact(tmp_path: Path) -> None:
    from autopilot_nodekit.codex_goal import build_codex_goal

    manifest = {
        "project": {"name": "Goal test", "goal": "Exercise native Codex goal generation."},
        "tasks": [
            {
                "id": "T001",
                "title": "Generate goal",
                "objective": "Produce a Codex /goal command from NodeKit task state.",
                "success_criteria": "The generated command names the task and the verifier.",
                "verifier": {"command": "python -m pytest -q", "timeout_seconds": 120},
                "memory": {"required_task_ids": ["T000"], "required_tags": ["goal"]},
            }
        ],
    }
    db = init_workspace(tmp_path, manifest, base_config("python -c 'print(0)'"))
    try:
        result = build_codex_goal(tmp_path, db, task_id="T001")
        goal = result["goal"]
        assert goal.startswith("/goal ")
        assert "T001" in goal
        assert "python -m pytest -q" in goal
        assert "Never mark passed unless the verifier passes" in goal
        assert result["length"] < 4000
        assert result["verifier"]["source"] == "task"
    finally:
        db.close()


def test_install_codex_native_enables_goals_feature(tmp_path: Path) -> None:
    from autopilot_nodekit.codex_native import install_codex_native_files

    install_codex_native_files(tmp_path, force=True)
    config = (tmp_path / ".codex" / "config.toml").read_text(encoding="utf-8")
    assert "[features]" in config
    assert "goals = true" in config


def test_figure_plan_generates_many_review_gated_tasks(tmp_path: Path) -> None:
    from autopilot_nodekit.figure_plan import generate_journal_figure_manifest, write_figure_manifest

    manifest = generate_journal_figure_manifest(figure_count=100, journal="Nature", tasks_per_figure=3)
    assert len(manifest["tasks"]) >= 200
    assert len(manifest["tasks"]) == 305
    write_figure_manifest(tmp_path, manifest)
    db = AutoDB(workspace_paths(tmp_path)["db"])
    db.init_schema()
    try:
        import_manifest(db, workspace_paths(tmp_path)["manifest"])
        assert db.get_task("G000_SETUP_REVIEW")["status"] == "review_pending"
        assert db.get_task("H000_PLAN_REVIEW")["status"] == "review_pending"
        assert db.claim_ready_task("w") is None
        db.approve_task("G000_SETUP_REVIEW", summary="setup approved")
        assert db.claim_ready_task("w") is None
        db.approve_task("H000_PLAN_REVIEW", summary="approved")
        claim = db.claim_ready_task("w")
        assert claim is not None
        task, _ = claim
        assert task["id"] == "H010_BOUNDARY_PERMISSION_TEST"
    finally:
        db.close()


def test_pilot_gate_blocks_bulk_until_human_approval(tmp_path: Path) -> None:
    from autopilot_nodekit.figure_plan import generate_journal_figure_manifest, write_figure_manifest

    manifest = generate_journal_figure_manifest(figure_count=3, journal="Science", tasks_per_figure=3)
    write_figure_manifest(tmp_path, manifest)
    db = AutoDB(workspace_paths(tmp_path)["db"])
    db.init_schema()
    try:
        import_manifest(db, workspace_paths(tmp_path)["manifest"])
        for tid in ["G000_SETUP_REVIEW", "H000_PLAN_REVIEW", "H010_BOUNDARY_PERMISSION_TEST", "F001_SPEC", "F001_RENDER", "F001_QC"]:
            db.approve_task(tid, summary=f"test approved {tid}", require_gates=False)
        assert db.get_task("H020_PILOT_REVIEW")["status"] == "review_pending"
        assert db.get_task("F002_SPEC")["status"] == "planned"
        assert db.claim_ready_task("w") is None
        db.approve_task("H020_PILOT_REVIEW", summary="pilot approved")
        claim = db.claim_ready_task("w")
        assert claim is not None
        task, _ = claim
        assert task["id"] == "F002_SPEC"
    finally:
        db.close()


def test_interactive_codex_prepare_and_finish(tmp_path: Path) -> None:
    from autopilot_nodekit.figure_plan import generate_journal_figure_manifest, write_figure_manifest
    from autopilot_nodekit.runner import finish_prepared_codex_run, prepare_interactive_codex_run

    manifest = generate_journal_figure_manifest(figure_count=1, journal="Nature", tasks_per_figure=3)
    write_figure_manifest(tmp_path, manifest)
    from autopilot_nodekit.codex_native import install_codex_native_files
    install_codex_native_files(tmp_path, force=True)
    dump_yaml(workspace_paths(tmp_path)["config"], base_config("python -c 'print(0)'"))
    db = AutoDB(workspace_paths(tmp_path)["db"])
    db.init_schema()
    try:
        import_manifest(db, workspace_paths(tmp_path)["manifest"])
        assert prepare_interactive_codex_run(tmp_path, db, "codex-test") is None
        db.approve_task("G000_SETUP_REVIEW", summary="setup approved")
        assert prepare_interactive_codex_run(tmp_path, db, "codex-test") is None
        db.approve_task("H000_PLAN_REVIEW", summary="approved")
        run_id = prepare_interactive_codex_run(tmp_path, db, "codex-test")
        assert run_id is not None
        run_dir = tmp_path / "runs" / run_id
        assert (run_dir / "open_codex.sh").exists()
        assert db.get_task("H010_BOUNDARY_PERMISSION_TEST")["status"] == "running"
        (run_dir / "worker_result.json").write_text(json.dumps({
            "status": "passed",
            "summary": "ok",
            "details": "ok",
            "memory_nodes": [],
            "review": {
                "policy": "santa_dual_review",
                "reviewer_a": {"agent": "autopilot-santa-reviewer-a", "status": "NICE", "summary": "Verifier evidence is present.", "evidence": ["boundary command passed"]},
                "reviewer_b": {"agent": "autopilot-santa-reviewer-b", "status": "NICE", "summary": "Scope and permissions respected.", "evidence": ["no forbidden writes"]},
                "fixes_after_review": []
            }
        }), encoding="utf-8")
        status = finish_prepared_codex_run(tmp_path, db, run_id)
        assert status == "passed"
        assert db.get_task("H010_BOUNDARY_PERMISSION_TEST")["status"] == "passed"
    finally:
        db.close()


def test_reset_graph_removes_residual_ready_tasks_before_generated_plan(tmp_path: Path) -> None:
    db = init_workspace(
        tmp_path,
        {"tasks": [{"id": "OLD", "title": "Old", "objective": "old", "success_criteria": "old"}]},
        base_config("python -c 'print(0)'"),
    )
    try:
        assert db.get_task("OLD")["status"] == "ready"
        db.reset_graph(keep_memory=False)
        from autopilot_nodekit.figure_plan import generate_journal_figure_manifest, write_figure_manifest

        manifest = generate_journal_figure_manifest(figure_count=2, journal="Nature", tasks_per_figure=3)
        write_figure_manifest(tmp_path, manifest)
        import_manifest(db, workspace_paths(tmp_path)["manifest"])
        assert db.get_task("OLD") is None
        assert db.claim_ready_task("w") is None
    finally:
        db.close()


def test_project_spec_from_chinese_prompt_fast_mode_generates_single_start_gate(tmp_path: Path) -> None:
    from autopilot_nodekit.project_spec import infer_project_spec_from_prompt, spec_to_figure_plan_kwargs, write_project_spec
    from autopilot_nodekit.figure_plan import generate_journal_figure_manifest, write_figure_manifest
    from autopilot_nodekit.codex_native import install_codex_native_files

    prompt = "我要做100个期刊图，目标期刊 Nature。每张图必须有源数据、脚本、PDF/PNG/SVG、caption 和QC记录，不能伪造数据。"
    spec = infer_project_spec_from_prompt(prompt, gate_mode="fast")
    assert spec["project"]["artifact_count"] == 100
    assert spec["project"]["journal"] == "Nature"
    assert spec["planning"]["gate_mode"] == "fast"
    write_project_spec(tmp_path, spec, prompt_text=prompt)
    install_codex_native_files(tmp_path, force=True)
    manifest = generate_journal_figure_manifest(**spec_to_figure_plan_kwargs(spec))
    write_figure_manifest(tmp_path, manifest)
    assert len(manifest["tasks"]) == 303
    task_ids = {t["id"] for t in manifest["tasks"]}
    assert "G000_START_REVIEW" in task_ids
    assert "G000_SETUP_REVIEW" not in task_ids
    assert "H000_PLAN_REVIEW" not in task_ids
    assert "H020_PILOT_REVIEW" not in task_ids
    assert manifest["project"]["gate_mode"] == "fast"

    db = AutoDB(workspace_paths(tmp_path)["db"])
    db.init_schema()
    try:
        import_manifest(db, workspace_paths(tmp_path)["manifest"])
        assert db.claim_ready_task("w") is None
        db.approve_task("G000_START_REVIEW", summary="startup approved")
        claim = db.claim_ready_task("w")
        assert claim is not None
        task, _ = claim
        assert task["id"] == "H010_BOUNDARY_PERMISSION_TEST"
        # F002 cannot release until the automatic F001_QC pilot guard passes.
        assert db.get_task("F002_SPEC")["status"] == "planned"
    finally:
        db.close()


def test_balanced_mode_keeps_only_start_and_pilot_human_gates(tmp_path: Path) -> None:
    from autopilot_nodekit.figure_plan import generate_journal_figure_manifest, write_figure_manifest
    from autopilot_nodekit.codex_native import install_codex_native_files

    manifest = generate_journal_figure_manifest(figure_count=10, journal="Nature", tasks_per_figure=3, gate_mode="balanced")
    assert len(manifest["tasks"]) == 34
    task_ids = {t["id"] for t in manifest["tasks"]}
    assert {"G000_START_REVIEW", "H020_PILOT_REVIEW"}.issubset(task_ids)
    assert "G000_SETUP_REVIEW" not in task_ids
    assert "H000_PLAN_REVIEW" not in task_ids
    write_figure_manifest(tmp_path, manifest)
    install_codex_native_files(tmp_path, force=True)
    db = AutoDB(workspace_paths(tmp_path)["db"])
    db.init_schema()
    try:
        import_manifest(db, workspace_paths(tmp_path)["manifest"])
        from autopilot_nodekit.cli import validate_graph
        report = validate_graph(db, tmp_path, strict=True)
        assert report["errors"] == []
    finally:
        db.close()


def test_codex_draft_spec_prepares_replayable_script(tmp_path: Path) -> None:
    from autopilot_nodekit.project_spec import prepare_codex_spec_draft

    prompt = tmp_path / "PROJECT_PROMPT.md"
    prompt.write_text("Generate 12 journal figures for Nature. Never fabricate data.", encoding="utf-8")
    info = prepare_codex_spec_draft(tmp_path, prompt, gate_mode="fast")
    assert Path(info["script"]).exists()
    assert Path(info["goal_path"]).exists()
    goal = Path(info["goal_path"]).read_text(encoding="utf-8")
    assert goal.startswith("/goal")
    assert "PROJECT_SPEC.yml" in goal
    assert "gate_mode=fast" in goal
    script = Path(info["script"]).read_text(encoding="utf-8")
    assert "codex exec" in script
    assert "--sandbox workspace-write" in script
