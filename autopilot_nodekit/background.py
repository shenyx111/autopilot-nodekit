from __future__ import annotations

import json
import os
import platform
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .bootstrap import install_nodekit_runtime, package_root
from .util import load_yaml, read_json, read_text, write_json, write_text


def detect_background_backends(workspace: Path | None = None) -> Dict[str, Any]:
    system = platform.system().lower()
    is_windows = system.startswith("windows")
    workspace = workspace.resolve() if workspace else None
    env = _runtime_env()
    backends: List[Dict[str, Any]] = []
    checks: List[Dict[str, Any]] = []

    def add(name: str, available: bool, detail: str, command_example: str, recommended: bool = False) -> None:
        backends.append(
            {
                "name": name,
                "available": bool(available),
                "detail": detail,
                "command_example": command_example,
                "recommended": bool(recommended),
            }
        )

    tmux_path = shutil.which("tmux")
    tmux_ok = False
    tmux_detail = tmux_path or "not found"
    if tmux_path and not is_windows:
        tmux_ok, tmux_detail = _tmux_smoke(tmux_path, env)
    add("tmux", (not is_windows) and tmux_ok, tmux_detail, "tmux new-session -d -s <session> '<command>'", recommended=(not is_windows and tmux_ok))

    nohup_path = shutil.which("nohup")
    add("nohup", (not is_windows) and bool(nohup_path), nohup_path or "not found", "nohup <command> > logs/background/<id>.log 2>&1 &")

    setsid_path = shutil.which("setsid")
    add("setsid", (not is_windows) and bool(setsid_path), setsid_path or "not found", "setsid sh -c '<command>' &")

    # Pure Python detached backend is the safest Windows default and a useful fallback on Linux.
    add("detached", True, f"python subprocess.Popen via {sys.executable}", "python -m autopilot_nodekit launch-background --backend detached", recommended=is_windows)

    pwsh_path = shutil.which("pwsh") or shutil.which("powershell") or shutil.which("powershell.exe")
    add("powershell", bool(pwsh_path), pwsh_path or "not found", "Start-Process ... with separate stdout/stderr files")

    add("foreground", True, "always available", "python -m autopilot_nodekit worker-loop --max-cycles 0 ...")

    py_ok, py_detail = _python_import_check(env)
    checks.append({"name": "python_import_autopilot_nodekit", "ok": py_ok, "detail": py_detail})
    codex_ok, codex_detail = _codex_check()
    checks.append({"name": "codex_cli", "ok": codex_ok, "detail": codex_detail})

    if workspace:
        install_nodekit_runtime(workspace, force=False)
        checks.extend(_workspace_checks(workspace))

    preferred_order = ["detached", "powershell", "foreground"] if is_windows else ["tmux", "nohup", "setsid", "detached", "foreground"]
    selected = next((b["name"] for name in preferred_order for b in backends if b["name"] == name and b["available"]), "foreground")
    return {
        "platform": platform.platform(),
        "system": platform.system(),
        "python_executable": sys.executable,
        "package_root": str(package_root()),
        "selected": selected,
        "backends": backends,
        "checks": checks,
        "recommendation": _recommendation(selected, checks),
    }


def launch_background_worker(
    workspace: Path,
    *,
    worker_id: str,
    max_cycles: int = 0,
    sleep_seconds: int = 5,
    lease_seconds: int = 0,
    backend: Optional[str] = None,
    session_name: Optional[str] = None,
) -> Dict[str, Any]:
    workspace = workspace.resolve()
    install_nodekit_runtime(workspace, force=False)
    info = detect_background_backends(workspace)
    selected = backend or info["selected"]
    available = {b["name"]: b for b in info["backends"] if b["available"]}
    if selected not in available:
        raise SystemExit(f"Background backend {selected!r} is not available. Run background-doctor --workspace .")

    bg_dir = workspace / "logs" / "background"
    bg_dir.mkdir(parents=True, exist_ok=True)
    aut_dir = workspace / "automation" / "background"
    aut_dir.mkdir(parents=True, exist_ok=True)
    log_path = bg_dir / f"{worker_id}.log"
    err_path = bg_dir / f"{worker_id}.err.log"
    pid_path = aut_dir / f"{worker_id}.pid"
    launch_path = aut_dir / f"{worker_id}.launch.json"

    args = [
        sys.executable,
        "-m",
        "autopilot_nodekit",
        "worker-loop",
        "--workspace",
        str(workspace),
        "--worker-id",
        worker_id,
        "--max-cycles",
        str(int(max_cycles)),
        "--sleep-seconds",
        str(int(sleep_seconds)),
        "--lease-seconds",
        str(int(lease_seconds)),
    ]
    env = _runtime_env()
    run_meta: Dict[str, Any] = {
        "backend": selected,
        "worker_id": worker_id,
        "workspace": str(workspace),
        "argv": args,
        "python_executable": sys.executable,
        "package_root": str(package_root()),
        "max_cycles": max_cycles,
        "lease_seconds": lease_seconds,
        "timeout_policy": "No NodeKit wall-clock timeout; --max-cycles 0 means unlimited cycles; --lease-seconds 0 means no lease expiry.",
        "log_path": str(log_path),
        "stderr_path": str(err_path),
        "pid_path": str(pid_path),
        "launch_path": str(launch_path),
    }

    if selected == "tmux":
        session = session_name or f"autopilot-{worker_id}"
        existing = _tmux_has_session(session, env)
        if existing:
            run_meta.update({"started": False, "existing_session": True, "session_name": session, "attach_command": f"tmux attach -t {session}", "reason": "session already exists; use background-status or stop the existing session before restarting"})
            write_json(launch_path, run_meta)
            return run_meta
        quoted_args = " ".join(shlex.quote(a) for a in args)
        py_path = shlex.quote(_prepend_env(env, "PYTHONPATH"))
        path_val = shlex.quote(_prepend_env(env, "PATH"))
        cmd = f"cd {shlex.quote(str(workspace))} && export PYTHONPATH={py_path} PATH={path_val} && {quoted_args} >> {shlex.quote(str(log_path))} 2>> {shlex.quote(str(err_path))}"
        subprocess.run(["tmux", "new-session", "-d", "-s", session, cmd], check=True, env=env)
        run_meta.update({"started": True, "session_name": session, "attach_command": f"tmux attach -t {session}"})
    elif selected in {"nohup", "setsid"}:
        quoted_args = " ".join(shlex.quote(a) for a in args)
        prefix = "nohup" if selected == "nohup" else "setsid"
        full = f"cd {shlex.quote(str(workspace))} && PYTHONPATH={shlex.quote(env.get('PYTHONPATH',''))} PATH={shlex.quote(env.get('PATH',''))} {prefix} {quoted_args} >> {shlex.quote(str(log_path))} 2>> {shlex.quote(str(err_path))} & echo $!"
        proc = subprocess.run(full, shell=True, text=True, capture_output=True, check=True, env=env)
        pid = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else ""
        if pid:
            write_text(pid_path, pid + "\n")
        run_meta.update({"started": True, "pid": pid, "tail_command": f"tail -f {log_path}"})
    elif selected == "powershell":
        ps = shutil.which("pwsh") or shutil.which("powershell") or shutil.which("powershell.exe") or "powershell"
        ps_args = " ".join(_ps_quote(a) for a in args)
        ps_command = (
            f"$env:PYTHONPATH = {_ps_quote(env.get('PYTHONPATH',''))}; "
            f"Start-Process -FilePath {_ps_quote(sys.executable)} -ArgumentList {_ps_quote(' '.join(args[1:]))} "
            f"-WorkingDirectory {_ps_quote(str(workspace))} "
            f"-RedirectStandardOutput {_ps_quote(str(log_path))} "
            f"-RedirectStandardError {_ps_quote(str(err_path))} "
            "-PassThru | Select-Object -ExpandProperty Id"
        )
        proc = subprocess.run([ps, "-NoProfile", "-Command", ps_command], text=True, capture_output=True, check=True, env=env)
        pid = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else ""
        if pid:
            write_text(pid_path, pid + "\n")
        run_meta.update({"started": True, "pid": pid, "powershell_command": ps_command})
    elif selected == "detached":
        flags = 0
        kwargs: Dict[str, Any] = {}
        if platform.system().lower().startswith("windows"):
            flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
        else:
            kwargs["start_new_session"] = True
        log_f = log_path.open("ab")
        err_f = err_path.open("ab")
        proc = subprocess.Popen(args, cwd=str(workspace), stdout=log_f, stderr=err_f, stdin=subprocess.DEVNULL, env=env, creationflags=flags, **kwargs)
        write_text(pid_path, str(proc.pid) + "\n")
        run_meta.update({"started": True, "pid": proc.pid, "tail_command": f"tail -f {log_path}"})
    else:
        run_meta.update({"started": False, "foreground_command": f"cd {shlex.quote(str(workspace))} && {' '.join(shlex.quote(a) for a in args)}"})
        write_json(launch_path, run_meta)
        raise SystemExit("No detached backend available. Use the foreground_command or install tmux/nohup/pwsh.")

    write_json(launch_path, run_meta)
    return run_meta


def background_status(workspace: Path, worker_id: str = "codex-worker") -> Dict[str, Any]:
    workspace = workspace.resolve()
    aut_dir = workspace / "automation" / "background"
    log_dir = workspace / "logs" / "background"
    pid_text = read_text(aut_dir / f"{worker_id}.pid").strip()
    launch = read_json(aut_dir / f"{worker_id}.launch.json", default={}) or {}
    heartbeat = read_json(aut_dir / f"{worker_id}.heartbeat.json", default={}) or {}
    return {
        "worker_id": worker_id,
        "pid": pid_text,
        "launch": launch,
        "heartbeat": heartbeat,
        "log_path": str(log_dir / f"{worker_id}.log"),
        "stderr_path": str(log_dir / f"{worker_id}.err.log"),
        "heartbeat_path": str(aut_dir / f"{worker_id}.heartbeat.json"),
    }


def _runtime_env() -> Dict[str, str]:
    env = os.environ.copy()
    root = str(package_root())
    current = env.get("PYTHONPATH", "")
    parts = [root] + ([current] if current else [])
    env["PYTHONPATH"] = os.pathsep.join(parts)
    return env


def _prepend_env(env: Dict[str, str], key: str) -> str:
    return env.get(key, "")


def _python_import_check(env: Dict[str, str]) -> tuple[bool, str]:
    try:
        proc = subprocess.run([sys.executable, "-c", "import autopilot_nodekit; print(autopilot_nodekit.__version__)"], text=True, capture_output=True, timeout=15, env=env)
        return proc.returncode == 0, (proc.stdout or proc.stderr).strip()
    except Exception as exc:
        return False, str(exc)


def _codex_check() -> tuple[bool, str]:
    codex = shutil.which("codex")
    if not codex:
        return False, "codex not found on PATH"
    try:
        proc = subprocess.run([codex, "exec", "--help"], text=True, capture_output=True, timeout=20)
        text = (proc.stdout or proc.stderr).strip().splitlines()
        return proc.returncode == 0, "; ".join(text[:3])
    except Exception as exc:
        return False, str(exc)


def _workspace_checks(workspace: Path) -> List[Dict[str, Any]]:
    checks: List[Dict[str, Any]] = []
    cfg_path = workspace / "automation" / "config.yml"
    if cfg_path.exists():
        try:
            cfg = load_yaml(cfg_path)
            command = str(((cfg.get("worker") or {}).get("command")) or "").strip()
            checks.append({"name": "worker_command_non_empty", "ok": bool(command), "detail": command or "worker.command is empty"})
        except Exception as exc:
            checks.append({"name": "worker_config_load", "ok": False, "detail": str(exc)})
    cdx = workspace / ".codex" / "config.toml"
    text = read_text(cdx)
    if text:
        bad = "job_max_runtime_seconds = 0" in text.replace(" ", "") or "job_max_runtime_seconds=0" in text.replace(" ", "")
        checks.append({"name": "codex_runtime_config", "ok": not bad, "detail": "invalid job_max_runtime_seconds=0" if bad else "ok"})
    hooks = read_text(workspace / ".codex" / "hooks.json")
    if hooks:
        windows = platform.system().lower().startswith("windows")
        bad = windows and "/bin/sh" in hooks
        checks.append({"name": "codex_hook_platform", "ok": not bad, "detail": "Windows hook contains /bin/sh" if bad else "ok"})
    return checks


def _tmux_smoke(tmux_path: str, env: Dict[str, str]) -> tuple[bool, str]:
    session = f"nodekit-doctor-{os.getpid()}-{int(time.time())}"
    try:
        v = subprocess.run([tmux_path, "-V"], text=True, capture_output=True, timeout=10, env=env)
        if v.returncode != 0:
            return False, (v.stderr or v.stdout or "tmux -V failed").strip()
        subprocess.run([tmux_path, "new-session", "-d", "-s", session, "true"], text=True, capture_output=True, timeout=10, check=True, env=env)
        subprocess.run([tmux_path, "has-session", "-t", session], text=True, capture_output=True, timeout=10, check=True, env=env)
        subprocess.run([tmux_path, "kill-session", "-t", session], text=True, capture_output=True, timeout=10, env=env)
        return True, v.stdout.strip() or tmux_path
    except Exception as exc:
        try:
            subprocess.run([tmux_path, "kill-session", "-t", session], text=True, capture_output=True, timeout=5, env=env)
        except Exception:
            pass
        return False, f"tmux smoke failed: {exc}"


def _tmux_has_session(session: str, env: Dict[str, str]) -> bool:
    tmux = shutil.which("tmux")
    if not tmux:
        return False
    proc = subprocess.run([tmux, "has-session", "-t", session], text=True, capture_output=True, env=env)
    return proc.returncode == 0


def _recommendation(selected: str, checks: List[Dict[str, Any]]) -> str:
    failed = [c for c in checks if not c.get("ok")]
    if failed:
        return "Fix failed checks before approving startup or launching unattended background loop: " + ", ".join(c["name"] for c in failed)
    return f"Use backend {selected!r}; approve startup gate only after bootstrap checks pass."


def _ps_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"
