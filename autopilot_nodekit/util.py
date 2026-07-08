from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

UTC = timezone.utc


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value)


def slugify(value: str, max_len: int = 64) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip("-")
    return (value or "item")[:max_len]


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def read_text(path: Path, default: str = "") -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return default


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def read_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_yaml(path: Path) -> Dict[str, Any]:
    try:
        import yaml  # type: ignore
    except Exception as exc:  # pragma: no cover
        raise SystemExit("PyYAML is required. Install with: python -m pip install -r requirements.txt") from exc
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Expected YAML mapping at {path}")
    return data


def dump_yaml(path: Path, data: Dict[str, Any]) -> None:
    try:
        import yaml  # type: ignore
    except Exception as exc:  # pragma: no cover
        raise SystemExit("PyYAML is required. Install with: python -m pip install -r requirements.txt") from exc
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)


def command_exists(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def run_command(command: str, cwd: Path, env: Optional[Dict[str, str]] = None, timeout: Optional[int] = None) -> subprocess.CompletedProcess[str]:
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    return subprocess.run(command, shell=True, cwd=str(cwd), env=merged_env, text=True, capture_output=True, timeout=timeout)


def append_jsonl(path: Path, event: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


def workspace_paths(workspace: Path) -> Dict[str, Path]:
    workspace = workspace.resolve()
    return {
        "workspace": workspace,
        "automation": workspace / "automation",
        "db": workspace / "automation" / "autopilot.sqlite",
        "events": workspace / "automation" / "events.jsonl",
        "runs": workspace / "runs",
        "memory": workspace / "memory",
        "memory_nodes": workspace / "memory" / "nodes",
        "live_md": workspace / "automation" / "manifest.live.md",
        "live_tsv": workspace / "automation" / "manifest.live.tsv",
        "manifest": workspace / "automation" / "manifest.yml",
        "config": workspace / "automation" / "config.yml",
    }


def render_table(rows: Iterable[Iterable[Any]], headers: Iterable[str]) -> str:
    headers = [str(h) for h in headers]
    data = [[str(x) if x is not None else "" for x in row] for row in rows]
    widths = [len(h) for h in headers]
    for row in data:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))
    fmt = " | ".join("{:<" + str(w) + "}" for w in widths)
    lines = [fmt.format(*headers), "-+-".join("-" * w for w in widths)]
    lines.extend(fmt.format(*row) for row in data)
    return "\n".join(lines)
