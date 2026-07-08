#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        payload = {}
    cwd = Path(payload.get("cwd") or os.getcwd())
    manifest = cwd / "automation" / "manifest.yml"
    if not manifest.exists():
        print(json.dumps({"continue": True, "systemMessage": "Autopilot NodeKit hook skipped: automation/manifest.yml not found."}))
        return 0
    proc = subprocess.run(
        [sys.executable, "-m", "autopilot_nodekit", "render", "--workspace", str(cwd)],
        cwd=str(cwd),
        text=True,
        capture_output=True,
        timeout=25,
    )
    if proc.returncode == 0:
        message = "Autopilot NodeKit live manifest rendered."
    else:
        message = "Autopilot NodeKit render hook failed; inspect automation/ and package installation."
    print(json.dumps({"continue": True, "systemMessage": message}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
