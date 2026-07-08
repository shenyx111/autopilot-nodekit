from __future__ import annotations

import shlex
import subprocess
from pathlib import Path
from typing import Optional

from .util import command_exists, load_yaml, workspace_paths


def launch_tmux_worker(workspace: Path, worker_id: str, max_cycles: int = 0, session_name: Optional[str] = None) -> str:
    if not command_exists("tmux"):
        raise SystemExit("tmux is not installed or not on PATH.")
    paths = workspace_paths(workspace)
    config = load_yaml(paths["config"])
    prefix = ((config.get("tmux", {}) or {}).get("session_prefix") or "autopilot")
    session = session_name or f"{prefix}-{worker_id}"
    cmd = f"cd {shlex.quote(str(workspace))} && python -m autopilot_nodekit worker-loop --workspace . --worker-id {shlex.quote(worker_id)} --max-cycles {int(max_cycles)}"
    subprocess.run(["tmux", "new-session", "-d", "-s", session, cmd], check=True)
    return session
