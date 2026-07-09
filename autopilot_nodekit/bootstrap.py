from __future__ import annotations

import os
import platform
import shlex
import sys
from pathlib import Path
from typing import Any, Dict

from .util import write_json, write_text

NODEKIT_DIR = ".nodekit"


def package_root() -> Path:
    # .../autopilot_nodekit/bootstrap.py -> project/package root parent
    return Path(__file__).resolve().parents[1]


def platform_is_windows() -> bool:
    return platform.system().lower().startswith("windows")


def install_nodekit_runtime(workspace: Path, *, force: bool = False) -> Dict[str, Any]:
    """Install small cross-platform wrappers into the target workspace.

    The wrappers are intentionally simple and explicit. They fix the two most
    common bootstrap failures seen in real runs:

    - background processes cannot import autopilot_nodekit because PYTHONPATH was
      only set in the interactive shell;
    - Codex worker subprocesses inherit AUTOPILOT_* variables and confuse nested
      Codex sessions or result-file contracts.
    """
    workspace = workspace.resolve()
    nodekit = workspace / NODEKIT_DIR
    nodekit.mkdir(parents=True, exist_ok=True)
    root = package_root()
    py = Path(sys.executable).resolve()
    env = {
        "version": "0.9",
        "python_executable": str(py),
        "package_root": str(root),
        "workspace": str(workspace),
        "pathsep": os.pathsep,
    }
    write_json(nodekit / "env.json", env)

    nodekit_sh = f'''#!/usr/bin/env bash
set -euo pipefail
export PYTHONPATH={shlex.quote(str(root))}${{PYTHONPATH:+:${{PYTHONPATH}}}}
exec {shlex.quote(str(py))} -m autopilot_nodekit "$@"
'''
    codex_worker_sh = f'''#!/usr/bin/env bash
set -euo pipefail
RUN_DIR="${{AUTOPILOT_RUN_DIR:?AUTOPILOT_RUN_DIR is required}}"
PROMPT="${{AUTOPILOT_PROMPT:?AUTOPILOT_PROMPT is required}}"
# Keep only local variables for paths, then scrub NodeKit-specific env vars from the child Codex process.
env \
  -u AUTOPILOT_WORKSPACE \
  -u AUTOPILOT_RUN_DIR \
  -u AUTOPILOT_TASK_ID \
  -u AUTOPILOT_RUN_ID \
  -u AUTOPILOT_PROMPT \
  -u AUTOPILOT_CONTEXT_PACK \
  -u AUTOPILOT_VERIFIER_COMMAND \
  -u AUTOPILOT_VERIFIER_SOURCE \
  -u AUTOPILOT_VERIFIER_LOG \
  -u AUTOPILOT_CODEX_SKILLS_DIR \
  codex exec --sandbox workspace-write --skip-git-repo-check --output-last-message "$RUN_DIR/codex_final.md" - < "$PROMPT"
'''
    nodekit_ps1 = f'''$ErrorActionPreference = "Stop"
$env:PYTHONPATH = "{_ps_escape(str(root))}" + [System.IO.Path]::PathSeparator + $env:PYTHONPATH
& "{_ps_escape(str(py))}" -m autopilot_nodekit @args
exit $LASTEXITCODE
'''
    codex_worker_ps1 = '''$ErrorActionPreference = "Stop"
$RunDir = $env:AUTOPILOT_RUN_DIR
$Prompt = $env:AUTOPILOT_PROMPT
if (-not $RunDir) { throw "AUTOPILOT_RUN_DIR is required" }
if (-not $Prompt) { throw "AUTOPILOT_PROMPT is required" }
$Scrub = @(
  "AUTOPILOT_WORKSPACE",
  "AUTOPILOT_RUN_DIR",
  "AUTOPILOT_TASK_ID",
  "AUTOPILOT_RUN_ID",
  "AUTOPILOT_PROMPT",
  "AUTOPILOT_CONTEXT_PACK",
  "AUTOPILOT_VERIFIER_COMMAND",
  "AUTOPILOT_VERIFIER_SOURCE",
  "AUTOPILOT_VERIFIER_LOG",
  "AUTOPILOT_CODEX_SKILLS_DIR"
)
foreach ($Name in $Scrub) { Remove-Item "Env:$Name" -ErrorAction SilentlyContinue }
Get-Content -Raw $Prompt | codex exec --sandbox workspace-write --skip-git-repo-check --output-last-message (Join-Path $RunDir "codex_final.md") -
exit $LASTEXITCODE
'''
    files = {
        nodekit / "nodekit": nodekit_sh,
        nodekit / "codex_worker.sh": codex_worker_sh,
        nodekit / "nodekit.ps1": nodekit_ps1,
        nodekit / "codex_worker.ps1": codex_worker_ps1,
        nodekit / "README.md": "# NodeKit runtime wrappers\n\nUse these wrappers instead of relying on shell-specific PYTHONPATH state.\n",
    }
    for path, content in files.items():
        if path.exists() and not force:
            continue
        write_text(path, content)
        if path.suffix in {"", ".sh"}:
            try:
                path.chmod(0o755)
            except Exception:
                pass
    return env


def worker_command_for_platform(workspace: Path | None = None) -> str:
    if platform_is_windows():
        return 'powershell -NoProfile -ExecutionPolicy Bypass -File .nodekit/codex_worker.ps1'
    return 'bash .nodekit/codex_worker.sh'


def nodekit_command_for_platform(args: str = "") -> str:
    if platform_is_windows():
        return ('powershell -NoProfile -ExecutionPolicy Bypass -File .nodekit/nodekit.ps1 ' + args).strip()
    return ('bash .nodekit/nodekit ' + args).strip()


def _ps_escape(value: str) -> str:
    return value.replace('`', '``').replace('"', '`"')
