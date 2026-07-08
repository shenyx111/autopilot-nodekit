from __future__ import annotations

from pathlib import Path
import glob as globlib
from typing import Iterable


def verify_artifact(workspace: Path, pattern: str, min_bytes: int = 1, allowed_suffixes: Iterable[str] | None = None) -> tuple[bool, str]:
    workspace = workspace.resolve()
    if Path(pattern).is_absolute():
        search_pattern = pattern
    else:
        search_pattern = str(workspace / pattern)
    matches = [Path(p) for p in globlib.glob(search_pattern)]
    if not matches:
        return False, f"No artifact matched pattern: {pattern}"
    suffixes = {s.lower() for s in (allowed_suffixes or []) if s}
    good = []
    bad = []
    for path in matches:
        try:
            resolved = path.resolve()
            if not str(resolved).startswith(str(workspace)):
                bad.append(f"outside workspace: {path}")
                continue
            if suffixes and resolved.suffix.lower() not in suffixes:
                bad.append(f"suffix not allowed: {path}")
                continue
            size = resolved.stat().st_size
            if size < min_bytes:
                bad.append(f"too small ({size} bytes): {path}")
                continue
            good.append(f"{resolved.relative_to(workspace)} ({size} bytes)")
        except Exception as exc:
            bad.append(f"{path}: {exc}")
    if good:
        msg = "Verified artifacts:\n" + "\n".join(f"- {g}" for g in good)
        if bad:
            msg += "\nIgnored candidates:\n" + "\n".join(f"- {b}" for b in bad)
        return True, msg
    return False, "No matching artifact passed checks. Problems:\n" + "\n".join(f"- {b}" for b in bad)
