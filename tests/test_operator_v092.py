from __future__ import annotations

import json
import textwrap
from pathlib import Path

from autopilot_nodekit.db import AutoDB
from autopilot_nodekit.manifest import import_manifest
from autopilot_nodekit.operator import operator_step
from autopilot_nodekit.runner import worker_loop
from autopilot_nodekit.util import dump_yaml, workspace_paths


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


def pass_worker(tmp_path: Path) -> str:
    path = tmp_path / "pass_worker.py"
    path.write_text(textwrap.dedent(
        """
        import json, os, pathlib
        run_dir = pathlib.Path(os.environ['AUTOPILOT_RUN_DIR'])
        task_id = os.environ['AUTOPILOT_TASK_ID']
        payload = {
          'status': 'passed',
          'summary': f'{task_id} passed with evidence',
          'details': 'test worker produced deterministic pass',
          'responsible_files': [],
          'patch_summary': 'test patch',
          'verifier_output': 'test verifier',
          'review': {
            'policy': 'santa_dual_review',
            'reviewer_a': {'agent':'autopilot-santa-reviewer-a','status':'NICE','summary':'a ok','evidence':['worker_result.json']},
            'reviewer_b': {'agent':'autopilot-santa-reviewer-b','status':'NICE','summary':'b ok','evidence':['worker_result.json']},
            'fixes_after_review': []
          }
        }
        (run_dir / 'worker_result.json').write_text(json.dumps(payload), encoding='utf-8')
        """
    ), encoding="utf-8")
    return f"python {path}"


def base_config(command: str) -> dict:
    return {
        "worker": {"agent": "shell-test", "command": command, "timeout_seconds": 60},
        "verifier": {"command": "", "timeout_seconds": 60},
        "memory": {"inject_full_nodes": False, "max_nodes_total": 24, "include_raw_artifact_paths": True},
    }


def test_operator_step_adds_repair_without_user_prompt(tmp_path: Path) -> None:
    db = init_workspace(tmp_path, {"tasks": [{"id": "T001", "title": "fail", "objective": "x", "success_criteria": "x"}]}, base_config(pass_worker(tmp_path)))
    try:
        db.conn.execute("UPDATE tasks SET status='failed', result_summary='boom' WHERE id='T001'")
        report = operator_step(tmp_path, db)
        assert report["action"] == "add_repair_task"
        assert report["repair_task_id"] == "T001_REPAIR_01"
        assert db.get_task("T001_REPAIR_01") is not None
    finally:
        db.close()


def test_operator_pauses_after_repair_attempt_limit(tmp_path: Path) -> None:
    manifest = {"tasks": [
        {"id": "T001", "title": "fail", "objective": "x", "success_criteria": "x"},
        {"id": "T001_REPAIR_01", "parent_id": "T001", "title": "repair", "objective": "x", "success_criteria": "x"},
    ]}
    db = init_workspace(tmp_path, manifest, base_config(pass_worker(tmp_path)))
    try:
        db.conn.execute("UPDATE tasks SET status='failed', result_summary='original failed' WHERE id='T001'")
        db.conn.execute("UPDATE tasks SET status='failed', result_summary='repair failed' WHERE id='T001_REPAIR_01'")
        report = operator_step(tmp_path, db, max_auto_repair_depth=1)
        assert report["action"] == "pause_repair_depth_limit"
        assert report["handled"] is False
        assert report["repair_attempts"] == 1
        assert db.get_task("T001_REPAIR_02") is None
    finally:
        db.close()


def test_operator_step_resolves_passed_repair_without_user_prompt(tmp_path: Path) -> None:
    manifest = {"tasks": [
        {"id": "T001", "title": "fail", "objective": "x", "success_criteria": "x"},
        {"id": "T001_REPAIR_01", "parent_id": "T001", "title": "repair", "objective": "x", "success_criteria": "x"},
        {"id": "T002", "title": "downstream", "objective": "x", "success_criteria": "x", "depends_on": ["T001"]},
    ]}
    db = init_workspace(tmp_path, manifest, base_config(pass_worker(tmp_path)))
    try:
        db.conn.execute("UPDATE tasks SET status='failed' WHERE id='T001'")
        db.conn.execute("UPDATE tasks SET status='passed' WHERE id='T001_REPAIR_01'")
        report = operator_step(tmp_path, db)
        assert report["action"] == "resolve_by_repair"
        assert db.get_task("T001")["status"] == "superseded"
        edges = db.list_edges(from_task="T002", edge_type="depends_on")
        assert [e["to_task"] for e in edges] == ["T001_REPAIR_01"]
    finally:
        db.close()


def test_operator_marks_stale_running_run_failed_then_adds_repair(tmp_path: Path) -> None:
    db = init_workspace(tmp_path, {"tasks": [{"id": "T001", "title": "stale", "objective": "x", "success_criteria": "x"}]}, base_config(pass_worker(tmp_path)))
    try:
        claim = db.claim_ready_task("codex-worker", lease_seconds=0)
        assert claim is not None
        _, run_id = claim
        run_dir = tmp_path / "runs" / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        db.update_run_paths(run_id, agent="codex-cli", result_json_path=str(run_dir / "worker_result.json"))

        report = operator_step(tmp_path, db, stale_minutes=0)
        assert report["action"] == "recover_stale"
        assert report["handled"] is True
        assert db.get_task("T001")["status"] == "failed"

        repair_report = operator_step(tmp_path, db)
        assert repair_report["action"] == "add_repair_task"
        assert repair_report["repair_task_id"] == "T001_REPAIR_01"
    finally:
        db.close()


def test_operator_does_not_recover_run_with_live_heartbeat(tmp_path: Path, monkeypatch) -> None:
    from autopilot_nodekit import recovery

    db = init_workspace(tmp_path, {"tasks": [{"id": "T001", "title": "active", "objective": "x", "success_criteria": "x"}]}, base_config(pass_worker(tmp_path)))
    try:
        claim = db.claim_ready_task("codex-worker", lease_seconds=0)
        assert claim is not None
        _, run_id = claim
        run_dir = tmp_path / "runs" / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        bg_dir = tmp_path / "automation" / "background"
        bg_dir.mkdir(parents=True, exist_ok=True)
        (bg_dir / "codex-worker.heartbeat.json").write_text(json.dumps({"ts": "9999-01-01T00:00:00Z", "pid": 12345, "run_id": run_id}), encoding="utf-8")
        monkeypatch.setattr(recovery, "_pid_alive", lambda pid: True)

        report = operator_step(tmp_path, db, stale_minutes=0)
        assert report["action"] == "monitor_running_background_task"
        assert report["handled"] is False
        assert db.get_task("T001")["status"] == "running"
        assert not (run_dir / "worker_result.json").exists()
    finally:
        db.close()


def test_worker_loop_auto_operator_repairs_then_releases_downstream(tmp_path: Path) -> None:
    manifest = {"tasks": [
        {"id": "T001", "title": "fail", "objective": "x", "success_criteria": "x"},
        {"id": "T002", "title": "downstream", "objective": "x", "success_criteria": "x", "depends_on": ["T001"]},
    ]}
    db = init_workspace(tmp_path, manifest, base_config(pass_worker(tmp_path)))
    try:
        db.conn.execute("UPDATE tasks SET status='failed', result_summary='needs repair' WHERE id='T001'")
        cycles = worker_loop(tmp_path, db, "codex-worker", max_cycles=3, sleep_seconds=0, auto_operator=True)
        assert cycles == 3
        assert db.get_task("T001_REPAIR_01")["status"] == "passed"
        assert db.get_task("T001")["status"] == "superseded"
        assert db.get_task("T002")["status"] == "ready"
    finally:
        db.close()


def test_next_command_prefers_current_ready_over_historical_failed_repair(tmp_path: Path) -> None:
    from autopilot_nodekit.workflow import next_command
    manifest = {"tasks": [
        {"id": "F001_RENDER", "title": "render", "objective": "x", "success_criteria": "x", "manifest_order": 10},
        {"id": "F001_RENDER_REPAIR_01", "parent_id": "F001_RENDER", "title": "old repair", "objective": "x", "success_criteria": "x", "manifest_order": 11},
        {"id": "F002_SPEC", "title": "next mainline", "objective": "x", "success_criteria": "x", "manifest_order": 20},
    ]}
    db = init_workspace(tmp_path, manifest, base_config(pass_worker(tmp_path)))
    try:
        db.conn.execute("UPDATE tasks SET status='passed' WHERE id='F001_RENDER'")
        db.conn.execute("UPDATE tasks SET status='failed', result_summary='old repair failed' WHERE id='F001_RENDER_REPAIR_01'")
        db.conn.execute("UPDATE tasks SET status='ready' WHERE id='F002_SPEC'")
        info = next_command(tmp_path, db)
        assert info["phase"] == "execute_next_ready_task"
        assert info["task_id"] == "F002_SPEC"
    finally:
        db.close()


def test_next_command_ignores_historical_failed_repair_at_completion(tmp_path: Path) -> None:
    from autopilot_nodekit.workflow import next_command
    manifest = {"tasks": [
        {"id": "F001_RENDER", "title": "render", "objective": "x", "success_criteria": "x", "manifest_order": 10},
        {"id": "F001_RENDER_REPAIR_01", "parent_id": "F001_RENDER", "title": "old repair", "objective": "x", "success_criteria": "x", "manifest_order": 11},
        {"id": "F002_SPEC", "title": "next mainline", "objective": "x", "success_criteria": "x", "manifest_order": 20},
    ]}
    db = init_workspace(tmp_path, manifest, base_config(pass_worker(tmp_path)))
    try:
        db.conn.execute("UPDATE tasks SET status='passed' WHERE id='F001_RENDER'")
        db.conn.execute("UPDATE tasks SET status='failed', result_summary='old repair failed' WHERE id='F001_RENDER_REPAIR_01'")
        db.conn.execute("UPDATE tasks SET status='passed' WHERE id='F002_SPEC'")
        info = next_command(tmp_path, db)
        assert info["phase"] == "complete_or_no_ready_work"
    finally:
        db.close()


def test_next_command_repairs_failed_task_that_blocks_downstream(tmp_path: Path) -> None:
    from autopilot_nodekit.workflow import next_command
    manifest = {"tasks": [
        {"id": "T001", "title": "failed blocker", "objective": "x", "success_criteria": "x", "manifest_order": 10},
        {"id": "T002", "title": "downstream", "objective": "x", "success_criteria": "x", "manifest_order": 20, "depends_on": ["T001"]},
    ]}
    db = init_workspace(tmp_path, manifest, base_config(pass_worker(tmp_path)))
    try:
        db.conn.execute("UPDATE tasks SET status='failed', result_summary='boom' WHERE id='T001'")
        db.conn.execute("UPDATE tasks SET status='planned' WHERE id='T002'")
        info = next_command(tmp_path, db)
        assert info["phase"] == "repair_required"
        assert info["task_id"] == "T001"
    finally:
        db.close()
