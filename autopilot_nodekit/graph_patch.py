from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from .db import AutoDB
from .util import read_json, write_json


def apply_graph_patch(db: AutoDB, patch: Dict[str, Any], source: str = "worker_result") -> int:
    operations = patch.get("operations") if isinstance(patch, dict) else None
    if not operations:
        return 0
    count = 0
    with db.transaction():
        for op in operations:
            db.apply_graph_operation(op)
            count += 1
        db.event("graph_patch_applied", {"source": source, "operation_count": count, "patch": patch})
        db.refresh_ready_tasks()
    return count


def load_patch(path: Path) -> Dict[str, Any]:
    data = read_json(path, default={})
    if not isinstance(data, dict):
        raise ValueError(f"Graph patch must be a JSON object: {path}")
    return data
