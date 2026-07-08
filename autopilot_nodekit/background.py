from __future__ import annotations

import os
import platform
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from .util import write_text


def detect_background_backends() -> Dict[str, Any]:
    system = platform.system().lower()
    is_windows = system.startswith("windows")
    backends: List[Dict[str, Any]] = []

    def add(name: str, available: bool, detail: str, command_example: str) -> None:
        backends.append({"name": name, "available": bool(available), "detail": detail, "command_example": command_example})

    tmux_path = shutil.which("tmux")
    add("tmux", bool(tmux_path), tmux_path or "not found", "tmux new-session -d -s <session> '<command>'")

    nohup_path = shutil.which("nohup")
    add("nohup", (not is_windows) and bool(nohup_path), nohup_path or "not found", "nohup <command> > automation/background/<id>.log 2>&1 &")

    setsid_path = shutil.which("setsid")
    add("setsid", (not is_windows) and bool(setsid_path), setsid_path or "not found", "setsid sh -c '<command>' &")

    pwsh_path = shutil.which("pwsh") or shutil.which("powershell") or shutil.which("powershell.exe")
    add("powershell", bool(pwsh_path), pwsh_path or "not found", "Start-Process powershell -ArgumentList '<command>'")

    add("foreground", True, "always available", "python -m autopilot_nodekit worker-loop --max-cycles 0 ...")

    preferred_order = ["tmux", "nohup", "setsid", "powershell", "foreground"] if not is_windows else ["powershell", "foreground"]
    selected = next((b["name"] for name in preferred_order for b in backends if b["name"] == name and b["available"]), "foreground")
    return {"platform": platform.platform(), "system": platform.system(), "selected": selected, "backends": backends}


def launch_background_worker(
    workspace: Path,
    *,
    worker_id: str,
    max_cycles: int = 0,
    sleep_seconds: int = 5,
    lease_seconds: int = 1800,
    backend: Optional[str] = None,
    session_name: Optional[str] = None,
) -> Dict[str, Any]:
    workspace = workspace.resolve()
    info = detect_background_backends()
    selected = backend or info["selected"]
    available = {b["name"]: b for b in info["backends"] if b["available"]}
    if selected not in available:
        raise SystemExit(f"Background backend {selected!r} is not available on this machine. Run background-doctor to inspect options.")

    bg_dir = workspace / "automation" / "background"
    bg_dir.mkdir(parents=True, exist_ok=True)
    log_path = bg_dir / f"{worker_id}.log"
    pid_path = bg_dir / f"{worker_id}.pid"
    command = (
        f"python -m autopilot_nodekit worker-loop --workspace . --worker-id {shlex.quote(worker_id)} "
        f"--max-cycles {int(max_cycles)} --sleep-seconds {int(sleep_seconds)} --lease-seconds {int(lease_seconds)}"
    )
    run_meta: Dict[str, Any] = {
        "backend": selected,
        "worker_id": worker_id,
        "workspace": str(workspace),
        "command": command,
        "max_cycles": max_cycles,
        "timeout_policy": "no NodeKit wall-clock timeout; --max-cycles 0 means unlimited cycles until no ready work remains or the process is stopped",
        "log_path": str(log_path),
    }

    if selected == "tmux":
        session = session_name or f"autopilot-{worker_id}"
        tmux_cmd = f"cd {shlex.quote(str(workspace))} && {command} 2>&1 | tee -a {shlex.quote(str(log_path))}"
        subprocess.run(["tmux", "new-session", "-d", "-s", session, tmux_cmd], check=True)
        run_meta.update({"session_name": session, "attach_command": f"tmux attach -t {session}"})
    elif selected == "nohup":
        full = f"cd {shlex.quote(str(workspace))} && nohup {command} > {shlex.quote(str(log_path))} 2>&1 & echo $!"
        proc = subprocess.run(full, shell=True, text=True, capture_output=True, check=True)
        pid = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else ""
        if pid:
            write_text(pid_path, pid + "\n")
        run_meta.update({"pid": pid, "pid_path": str(pid_path), "tail_command": f"tail -f {log_path}"})
    elif selected == "setsid":
        full = f"cd {shlex.quote(str(workspace))} && setsid sh -c {shlex.quote(command + ' >> ' + shlex.quote(str(log_path)) + ' 2>&1')} & echo $!"
        proc = subprocess.run(full, shell=True, text=True, capture_output=True, check=True)
        pid = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else ""
        if pid:
            write_text(pid_path, pid + "\n")
        run_meta.update({"pid": pid, "pid_path": str(pid_path), "tail_command": f"tail -f {log_path}"})
    elif selected == "powershell":
        ps = shutil.which("pwsh") or shutil.which("powershell") or shutil.which("powershell.exe")
        ps_command = (
            "Start-Process -FilePath python -ArgumentList "
            + shlex.quote(f"-m autopilot_nodekit worker-loop --workspace . --worker-id {worker_id} --max-cycles {max_cycles} --sleep-seconds {sleep_seconds} --lease-seconds {lease_seconds}")
            + f" -WorkingDirectory {shlex.quote(str(workspace))}"
        )
        subprocess.run([ps or "powershell", "-NoProfile", "-Command", ps_command], check=True)
        run_meta.update({"powershell_command": ps_command})
    else:
        run_meta.update({"foreground_command": f"cd {shlex.quote(str(workspace))} && {command}"})
        raise SystemExit("No detached backend available. Run the foreground_command printed by background-doctor or install tmux/nohup/pwsh.")

    return run_meta
