from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from .context import build_context_pack
from .db import AutoDB
from .graph_patch import apply_graph_patch
from .memory import create_memory_nodes_from_result
from .render import render_live_manifest
from .util import append_jsonl, load_yaml, now_iso, read_json, run_command, write_json, write_text, workspace_paths
from .verifier import select_verifier
from .santa_review import evaluate_santa_review
from .shell_safety import lint_shell_command, render_findings, should_block

PASS_LIKE = {"passed", "skipped"}


def run_once(workspace: Path, db: AutoDB, worker_id: str, lease_seconds: int = 1800) -> Optional[str]:
    paths = workspace_paths(workspace)
    config = load_yaml(paths["config"])
    claim = db.claim_ready_task(worker_id, lease_seconds=lease_seconds)
    if not claim:
        render_live_manifest(workspace, db)
        return None
    task, run_id = claim
    run_dir = paths["runs"] / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    build_context_pack(workspace, db, task["id"], run_id)

    worker = config.get("worker", {}) or {}
    agent = worker.get("agent", "shell")
    command = worker.get("command", "")
    timeout = int(worker.get("timeout_seconds", 3600)) if worker.get("timeout_seconds") else None
    db.update_run_paths(
        run_id,
        agent=agent,
        transcript_path=str(run_dir / "transcript.log"),
        stdout_path=str(run_dir / "stdout.log"),
        stderr_path=str(run_dir / "stderr.log"),
        result_json_path=str(run_dir / "worker_result.json"),
    )

    verifier = select_verifier(task, config)
    env = build_autopilot_env(workspace, run_dir, str(task["id"]), run_id, verifier)

    started = now_iso()
    exit_code: Optional[int] = None
    stdout = ""
    stderr = ""
    expanded = ""
    try:
        if not command:
            raise RuntimeError("worker.command is empty in automation/config.yml")
        expanded = expand_command(command, workspace=workspace, run_dir=run_dir, task_id=str(task["id"]), run_id=run_id)
        proc = run_command(expanded, cwd=workspace, env=env, timeout=timeout)
        exit_code = proc.returncode
        stdout, stderr = proc.stdout, proc.stderr
    except subprocess.TimeoutExpired as exc:
        exit_code = 124
        stdout = safe_text(exc.stdout)
        stderr = safe_text(exc.stderr) + f"\nTIMEOUT after {timeout} seconds"
    except Exception as exc:
        exit_code = 1
        stderr = f"Runner error: {exc}\n"

    write_text(run_dir / "stdout.log", stdout)
    write_text(run_dir / "stderr.log", stderr)
    write_text(
        run_dir / "transcript.log",
        f"# Run transcript\n\nstarted: {started}\nended: {now_iso()}\nagent: {agent}\ncommand: `{expanded or command}`\nexit_code: {exit_code}\n\n## stdout\n\n```\n{stdout}\n```\n\n## stderr\n\n```\n{stderr}\n```\n",
    )

    verifier_exit, effective_verifier = run_verifier_if_configured(workspace, config, task, run_dir, str(task["id"]), run_id, env)
    if effective_verifier.get("command"):
        db.update_run_paths(run_id, verifier_path=str(run_dir / "verifier.log"))

    result, inferred = read_worker_result_or_infer(run_dir / "worker_result.json", exit_code, verifier_exit)
    status = normalize_status(result.get("status"), exit_code)
    overrides: list[str] = []

    if exit_code not in (None, 0) and status in PASS_LIKE:
        status = "failed"
        overrides.append(f"worker command failed with exit_code={exit_code}")
    if verifier_exit not in (None, 0) and status in PASS_LIKE:
        status = "failed"
        overrides.append(f"verifier failed with exit_code={verifier_exit}")
    if effective_verifier.get("require_for_pass") and verifier_exit is None and status == "passed":
        status = "failed"
        overrides.append("pass requires a verifier, but no verifier command was configured")
    santa_ok, santa_errors, santa_meta = evaluate_santa_review(result, task, config)
    if status in PASS_LIKE and not santa_ok:
        status = "failed"
        overrides.append("Santa dual-review failed: " + "; ".join(santa_errors))

    if overrides:
        result = dict(result)
        result["status"] = status
        result["summary"] = append_sentence(str(result.get("summary") or default_summary(status, exit_code)), "autopilot override: " + "; ".join(overrides))
        result["details"] = append_sentence(str(result.get("details") or ""), "Autopilot status override: " + "; ".join(overrides))

    autopilot_meta = result.get("autopilot") if isinstance(result.get("autopilot"), dict) else {}
    autopilot_meta.update(
        {
            "normalized_status": status,
            "worker_exit_code": exit_code,
            "verifier_exit_code": verifier_exit,
            "verifier_source": effective_verifier.get("source", "none"),
            "verifier_command": effective_verifier.get("command", ""),
            "result_was_inferred": inferred,
            "status_overrides": overrides,
            "santa_review": santa_meta,
        }
    )
    result["autopilot"] = autopilot_meta

    summary = str(result.get("summary") or default_summary(status, exit_code))
    control_result = {
        "status": status,
        "summary": summary,
        "worker_exit_code": exit_code,
        "verifier_exit_code": verifier_exit,
        "verifier_source": effective_verifier.get("source", "none"),
        "santa_review": santa_meta,
        "result": result,
    }
    write_json(run_dir / "worker_result.normalized.json", result)
    write_json(run_dir / "control_result.json", control_result)

    create_memory_nodes_from_result(workspace, db, str(task["id"]), run_id, result, run_dir)

    patch_count = 0
    graph_patch = result.get("graph_patch")
    if isinstance(graph_patch, dict):
        write_json(run_dir / "graph_patch.json", graph_patch)
        db.update_run_paths(run_id, graph_patch_path=str(run_dir / "graph_patch.json"))
        patch_count = apply_graph_patch(db, graph_patch, source=str(run_dir / "worker_result.normalized.json"))

    db.complete_task_run(str(task["id"]), run_id, status, summary + (f"; graph_patch_ops={patch_count}" if patch_count else ""), exit_code=exit_code)
    render_live_manifest(workspace, db)
    return run_id


def prepare_interactive_codex_run(workspace: Path, db: AutoDB, worker_id: str, lease_seconds: int = 1800) -> Optional[str]:
    """Claim a ready task and prepare a per-task interactive Codex conversation.

    This does not execute Codex. It writes prompt/context/env/open scripts under runs/<run_id>/
    so the user can open a fresh Codex dialog for exactly one claimed task, then finish it
    with `codex-finish` after worker_result.json exists.
    """
    paths = workspace_paths(workspace)
    config = load_yaml(paths["config"])
    claim = db.claim_ready_task(worker_id, lease_seconds=lease_seconds)
    if not claim:
        render_live_manifest(workspace, db)
        return None
    task, run_id = claim
    run_dir = paths["runs"] / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    build_context_pack(workspace, db, task["id"], run_id)
    verifier = select_verifier(task, config)
    env = build_autopilot_env(workspace, run_dir, str(task["id"]), run_id, verifier)
    db.update_run_paths(
        run_id,
        agent="codex-interactive",
        transcript_path=str(run_dir / "interactive_transcript.md"),
        stdout_path=str(run_dir / "stdout.log"),
        stderr_path=str(run_dir / "stderr.log"),
        result_json_path=str(run_dir / "worker_result.json"),
    )
    env_lines = ["#!/usr/bin/env bash", "set -euo pipefail"]
    for key, value in env.items():
        env_lines.append(f"export {key}={shlex.quote(str(value))}")
    write_text(run_dir / "codex_env.sh", "\n".join(env_lines) + "\n")
    open_script = run_dir / "open_codex.sh"
    write_text(
        open_script,
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        f"source {shlex.quote(str(run_dir / 'codex_env.sh'))}\n"
        "cd \"$AUTOPILOT_WORKSPACE\"\n"
        "codex --cd \"$AUTOPILOT_WORKSPACE\" \"$(cat \"$AUTOPILOT_PROMPT\")\"\n",
    )
    try:
        os.chmod(open_script, 0o755)
        os.chmod(run_dir / "codex_env.sh", 0o755)
    except Exception:
        pass
    write_text(
        run_dir / "README_INTERACTIVE.md",
        f"""# Interactive Codex task

Task: `{task['id']}`
Run: `{run_id}`

Open a fresh Codex conversation for this exact task:

```bash
bash {open_script}
```

Inside Codex, complete the task and write:

```text
{run_dir / 'worker_result.json'}
```

Then finish and normalize the run:

```bash
python -m autopilot_nodekit codex-finish --workspace {shlex.quote(str(workspace))} --run-id {run_id}
```
""",
    )
    db.event("codex_interactive_prepared", {"open_script": str(open_script)}, task_id=str(task["id"]), run_id=run_id, worker_id=worker_id)
    render_live_manifest(workspace, db)
    return run_id


def finish_prepared_codex_run(workspace: Path, db: AutoDB, run_id: str, exit_code: Optional[int] = None) -> str:
    paths = workspace_paths(workspace)
    config = load_yaml(paths["config"])
    run = db.get_run(run_id)
    if run is None:
        raise KeyError(f"Run not found: {run_id}")
    task = db.get_task(run["task_id"])
    if task is None:
        raise KeyError(f"Task not found for run: {run['task_id']}")
    run_dir = paths["runs"] / run_id
    if exit_code is None:
        exit_code = 0 if (run_dir / "worker_result.json").exists() else 1
    env = build_autopilot_env(workspace, run_dir, str(task["id"]), run_id, select_verifier(task, config))
    write_text(run_dir / "stdout.log", read_existing(run_dir / "stdout.log"))
    write_text(run_dir / "stderr.log", read_existing(run_dir / "stderr.log"))
    verifier_exit, effective_verifier = run_verifier_if_configured(workspace, config, task, run_dir, str(task["id"]), run_id, env)
    if effective_verifier.get("command"):
        db.update_run_paths(run_id, verifier_path=str(run_dir / "verifier.log"))
    status, summary = finalize_control_result(workspace, db, task, run_id, run_dir, exit_code, verifier_exit, effective_verifier)
    render_live_manifest(workspace, db)
    return status


def build_autopilot_env(workspace: Path, run_dir: Path, task_id: str, run_id: str, verifier: Dict[str, Any]) -> Dict[str, str]:
    return {
        "AUTOPILOT_WORKSPACE": str(workspace),
        "AUTOPILOT_RUN_DIR": str(run_dir),
        "AUTOPILOT_TASK_ID": task_id,
        "AUTOPILOT_RUN_ID": run_id,
        "AUTOPILOT_PROMPT": str(run_dir / "prompt.md"),
        "AUTOPILOT_CONTEXT_PACK": str(run_dir / "context_pack.json"),
        "AUTOPILOT_VERIFIER_COMMAND": verifier.get("command", ""),
        "AUTOPILOT_VERIFIER_SOURCE": verifier.get("source", "none"),
        "AUTOPILOT_VERIFIER_LOG": str(run_dir / "verifier.log"),
        "AUTOPILOT_CODEX_SKILLS_DIR": str(workspace / ".agents" / "skills"),
        "PYTHONPATH": os.pathsep.join([str(Path(__file__).resolve().parents[1]), os.environ.get("PYTHONPATH", "")]).rstrip(os.pathsep),
    }


def finalize_control_result(workspace: Path, db: AutoDB, task: Any, run_id: str, run_dir: Path, exit_code: Optional[int], verifier_exit: Optional[int], effective_verifier: Dict[str, Any]) -> Tuple[str, str]:
    config = load_yaml(workspace_paths(workspace)["config"])
    result, inferred = read_worker_result_or_infer(run_dir / "worker_result.json", exit_code, verifier_exit)
    status = normalize_status(result.get("status"), exit_code)
    overrides: list[str] = []
    if exit_code not in (None, 0) and status in PASS_LIKE:
        status = "failed"
        overrides.append(f"worker command failed with exit_code={exit_code}")
    if verifier_exit not in (None, 0) and status in PASS_LIKE:
        status = "failed"
        overrides.append(f"verifier failed with exit_code={verifier_exit}")
    if effective_verifier.get("require_for_pass") and verifier_exit is None and status == "passed":
        status = "failed"
        overrides.append("pass requires a verifier, but no verifier command was configured")
    santa_ok, santa_errors, santa_meta = evaluate_santa_review(result, task, config)
    if status in PASS_LIKE and not santa_ok:
        status = "failed"
        overrides.append("Santa dual-review failed: " + "; ".join(santa_errors))
    if overrides:
        result = dict(result)
        result["status"] = status
        result["summary"] = append_sentence(str(result.get("summary") or default_summary(status, exit_code)), "autopilot override: " + "; ".join(overrides))
        result["details"] = append_sentence(str(result.get("details") or ""), "Autopilot status override: " + "; ".join(overrides))
    autopilot_meta = result.get("autopilot") if isinstance(result.get("autopilot"), dict) else {}
    autopilot_meta.update({
        "normalized_status": status,
        "worker_exit_code": exit_code,
        "verifier_exit_code": verifier_exit,
        "verifier_source": effective_verifier.get("source", "none"),
        "verifier_command": effective_verifier.get("command", ""),
        "result_was_inferred": inferred,
        "status_overrides": overrides,
        "santa_review": santa_meta,
    })
    result["autopilot"] = autopilot_meta
    summary = str(result.get("summary") or default_summary(status, exit_code))
    control_result = {
        "status": status,
        "summary": summary,
        "worker_exit_code": exit_code,
        "verifier_exit_code": verifier_exit,
        "verifier_source": effective_verifier.get("source", "none"),
        "santa_review": santa_meta,
        "result": result,
    }
    write_json(run_dir / "worker_result.normalized.json", result)
    write_json(run_dir / "control_result.json", control_result)
    create_memory_nodes_from_result(workspace, db, str(task["id"]), run_id, result, run_dir)
    patch_count = 0
    graph_patch = result.get("graph_patch")
    if isinstance(graph_patch, dict):
        write_json(run_dir / "graph_patch.json", graph_patch)
        db.update_run_paths(run_id, graph_patch_path=str(run_dir / "graph_patch.json"))
        patch_count = apply_graph_patch(db, graph_patch, source=str(run_dir / "worker_result.normalized.json"))
    db.complete_task_run(str(task["id"]), run_id, status, summary + (f"; graph_patch_ops={patch_count}" if patch_count else ""), exit_code=exit_code)
    return status, summary


def read_existing(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def worker_loop(
    workspace: Path,
    db: AutoDB,
    worker_id: str,
    max_cycles: int = 100,
    sleep_seconds: int = 5,
    lease_seconds: int = 0,
    auto_operator: bool = True,
    operator_stale_minutes: float = 30.0,
    max_auto_repair_depth: int = 3,
) -> int:
    cycles = 0
    idle = 0
    _write_worker_heartbeat(workspace, worker_id, phase="started", cycle=cycles, detail="worker-loop started")
    while max_cycles <= 0 or cycles < max_cycles:
        _write_worker_heartbeat(workspace, worker_id, phase="cycle_start", cycle=cycles + 1)
        run_id = run_once(workspace, db, worker_id, lease_seconds=lease_seconds)
        cycles += 1
        if run_id is None:
            operator_action = None
            if auto_operator:
                try:
                    from .operator import operator_step

                    operator_action = operator_step(
                        workspace,
                        db,
                        worker_id=worker_id,
                        stale_minutes=operator_stale_minutes,
                        max_auto_repair_depth=max_auto_repair_depth,
                        start_background=False,
                    )
                except Exception as exc:
                    operator_action = {"action": "operator_error", "error": str(exc), "handled": False}
            handled = bool(isinstance(operator_action, dict) and operator_action.get("handled"))
            if handled:
                idle = 0
                _write_worker_heartbeat(workspace, worker_id, phase="operator_handled", cycle=cycles, detail=str(operator_action.get("action")))
                time.sleep(min(1, max(0, sleep_seconds)))
                continue
            idle += 1
            detail = f"no ready task; idle_count={idle}"
            if operator_action:
                detail += f"; operator_action={operator_action.get('action')}"
            _write_worker_heartbeat(workspace, worker_id, phase="idle", cycle=cycles, detail=detail)
            if idle >= 3 and max_cycles > 0:
                _write_worker_heartbeat(workspace, worker_id, phase="stopped_idle", cycle=cycles, detail="no ready tasks after 3 idle polls")
                break
            time.sleep(sleep_seconds)
        else:
            idle = 0
            try:
                run = db.get_run(run_id)
                task_id = run["task_id"] if run is not None else None
            except Exception:
                task_id = None
            _write_worker_heartbeat(workspace, worker_id, phase="run_completed", cycle=cycles, run_id=run_id, task_id=task_id)
    _write_worker_heartbeat(workspace, worker_id, phase="exited", cycle=cycles, detail="worker-loop exited")
    return cycles


def _write_worker_heartbeat(workspace: Path, worker_id: str, *, phase: str, cycle: int, run_id: str | None = None, task_id: str | None = None, detail: str = "") -> None:
    paths = workspace_paths(workspace)
    bg_dir = paths["automation"] / "background"
    log_dir = workspace / "logs" / "background"
    bg_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "ts": now_iso(),
        "worker_id": worker_id,
        "pid": os.getpid(),
        "phase": phase,
        "cycle": cycle,
        "run_id": run_id,
        "task_id": task_id,
        "detail": detail,
    }
    write_json(bg_dir / f"{worker_id}.heartbeat.json", payload)
    append_jsonl(bg_dir / f"{worker_id}.heartbeat.jsonl", payload)
    append_jsonl(log_dir / f"{worker_id}.heartbeat.jsonl", payload)


def run_verifier_if_configured(workspace: Path, config: Dict[str, Any], task: Any, run_dir: Path, task_id: str, run_id: str, env: Dict[str, str]) -> Tuple[Optional[int], Dict[str, Any]]:
    verifier = select_verifier(task, config)
    command = verifier.get("command") or ""
    if not command.strip():
        return None, verifier
    timeout = verifier.get("timeout_seconds")
    expanded = expand_command(command, workspace=workspace, run_dir=run_dir, task_id=task_id, run_id=run_id)

    # v0.9.1: deterministic verifiers must be read-only and shell-safe. This
    # prevents accidents such as backtick command substitution in report text
    # causing an empty sbatch/scancel/rm-style command to execute. Operators can
    # opt in only for exceptional migrations by setting NODEKIT_ALLOW_RISKY_VERIFIER=1.
    findings = lint_shell_command(expanded, purpose="verifier", platform=os.name)
    if findings and should_block(findings) and env.get("NODEKIT_ALLOW_RISKY_VERIFIER") != "1":
        rendered = render_findings(findings)
        write_text(
            run_dir / "verifier.log",
            f"# verifier blocked by shell-safety lint\n\nsource: `{verifier.get('source')}`\ncommand: `{command}`\nexpanded: `{expanded}`\nexit_code: 126\n\n## findings\n{rendered}\n\nSet NODEKIT_ALLOW_RISKY_VERIFIER=1 only after human review if this verifier is intentionally side-effecting.\n",
        )
        return 126, verifier

    try:
        proc = run_command(expanded, cwd=workspace, env=env, timeout=timeout)
        write_text(
            run_dir / "verifier.log",
            f"# verifier\n\nsource: `{verifier.get('source')}`\ncommand: `{command}`\nexpanded: `{expanded}`\nexit_code: {proc.returncode}\n\n## shell-safety\n{render_findings(findings)}\n\n## stdout\n```\n{proc.stdout}\n```\n\n## stderr\n```\n{proc.stderr}\n```\n",
        )
        return proc.returncode, verifier
    except subprocess.TimeoutExpired as exc:
        write_text(run_dir / "verifier.log", f"# verifier timeout\n\nsource: `{verifier.get('source')}`\ncommand: `{command}`\ntimeout_seconds: {timeout}\nexit_code: 124\n\n{exc}\n")
        return 124, verifier
    except Exception as exc:
        write_text(run_dir / "verifier.log", f"# verifier runner error\n\nsource: `{verifier.get('source')}`\ncommand: `{command}`\nexit_code: 1\n\n{exc}\n")
        return 1, verifier


def read_worker_result_or_infer(path: Path, exit_code: Optional[int], verifier_exit: Optional[int]) -> Tuple[Dict[str, Any], bool]:
    try:
        result = read_json(path, default=None)
    except json.JSONDecodeError as exc:
        invalid_path = path.with_name("worker_result.invalid.json")
        if path.exists():
            shutil.move(str(path), str(invalid_path))
        result = infer_result(exit_code if exit_code not in (None, 0) else 1, verifier_exit)
        result["status"] = "failed"
        result["summary"] = f"Invalid worker_result.json: {exc}"
        result["details"] = f"The worker wrote malformed JSON. The raw invalid file was preserved at {invalid_path}."
        result["memory_nodes"] = [
            {
                "title": "Malformed worker_result.json",
                "scope": "bug",
                "tags": ["worker-result", "malformed-json", "runner"],
                "content": f"worker_result.json could not be parsed: {exc}. Inspect worker_result.invalid.json and transcript.log.",
                "raw_artifacts": ["worker_result.invalid.json", "transcript.log", "stdout.log", "stderr.log"],
                "confidence": 0.95,
            }
        ]
        write_json(path, result)
        return result, True
    if not isinstance(result, dict):
        result = infer_result(exit_code, verifier_exit)
        write_json(path, result)
        return result, True
    return result, False


def expand_command(command: str, workspace: Path, run_dir: Path, task_id: str, run_id: str) -> str:
    replacements = {
        "{workspace}": shlex.quote(str(workspace)),
        "{run_dir}": shlex.quote(str(run_dir)),
        "{prompt}": shlex.quote(str(run_dir / "prompt.md")),
        "{context}": shlex.quote(str(run_dir / "context_pack.json")),
        "{task_id}": shlex.quote(task_id),
        "{run_id}": shlex.quote(run_id),
    }
    expanded = command
    for key, value in replacements.items():
        expanded = expanded.replace(key, value)
    return expanded


def infer_result(exit_code: Optional[int], verifier_exit: Optional[int]) -> Dict[str, Any]:
    passed = exit_code == 0 and verifier_exit in (None, 0)
    return {
        "status": "passed" if passed else "failed",
        "summary": "Worker command exited successfully." if passed else f"Worker or verifier failed: exit_code={exit_code}, verifier_exit={verifier_exit}",
        "details": "No valid worker_result.json was produced; status inferred by autopilot-nodekit from exit codes.",
        "memory_nodes": [
            {
                "title": "Inferred run result",
                "scope": "task",
                "tags": ["inferred", "runner"],
                "content": f"Run status inferred from exit_code={exit_code}, verifier_exit={verifier_exit}. Inspect raw logs for details.",
                "confidence": 0.4,
            }
        ],
    }


def normalize_status(status: Any, exit_code: Optional[int]) -> str:
    s = str(status or "").strip().lower()
    if s in {"passed", "failed", "blocked", "skipped"}:
        return s
    return "passed" if exit_code == 0 else "failed"


def default_summary(status: str, exit_code: Optional[int]) -> str:
    return f"status={status}, exit_code={exit_code}"


def append_sentence(base: str, sentence: str) -> str:
    base = base.strip()
    sentence = sentence.strip()
    if not base:
        return sentence
    if base.endswith((".", ";", "!", "?")):
        return f"{base} {sentence}"
    return f"{base}. {sentence}"


def safe_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)
