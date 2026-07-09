from __future__ import annotations

import json
import re
import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .util import append_jsonl, now_iso, read_text

VALID_STATUSES = {"review_pending", "planned", "ready", "running", "passed", "failed", "blocked", "skipped", "superseded"}
TERMINAL_STATUSES = {"passed", "failed", "blocked", "skipped", "superseded"}
GATING_EDGE_TYPES = {"depends_on", "after_attempt", "blocked_by"}
EDGE_LIST_FIELDS = {
    "depends_on": "depends_on",
    "after_attempt": "after_attempt",
    "after_attempts": "after_attempt",
    "after_tasks": "after_attempt",
    "blocked_by": "blocked_by",
    "inserted_before": "inserted_before",
}


class AutoDB:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(db_path), timeout=30, isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")

    def close(self) -> None:
        self.conn.close()

    def init_schema(self) -> None:
        schema_path = Path(__file__).with_name("schema.sql")
        self.conn.executescript(read_text(schema_path))
        self._migrate()

    def _migrate(self) -> None:
        """Small idempotent migrations for users upgrading an existing local DB."""
        columns = {row["name"] for row in self.conn.execute("PRAGMA table_info(tasks)")}
        if "memory_policy_json" not in columns:
            self.conn.execute("ALTER TABLE tasks ADD COLUMN memory_policy_json TEXT")
        if "verifier_json" not in columns:
            self.conn.execute("ALTER TABLE tasks ADD COLUMN verifier_json TEXT")
        if "task_contract_json" not in columns:
            self.conn.execute("ALTER TABLE tasks ADD COLUMN task_contract_json TEXT")
        run_columns = {row["name"] for row in self.conn.execute("PRAGMA table_info(task_runs)")}
        if "memory_selection_path" not in run_columns:
            self.conn.execute("ALTER TABLE task_runs ADD COLUMN memory_selection_path TEXT")
        if "verifier_path" not in run_columns:
            self.conn.execute("ALTER TABLE task_runs ADD COLUMN verifier_path TEXT")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_parent ON tasks(parent_id)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_memory_status ON memory_nodes(status, updated_at)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_edges_from ON task_edges(from_task, edge_type)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_edges_to ON task_edges(to_task, edge_type)")

    @contextmanager
    def transaction(self):
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            yield
        except Exception:
            self.conn.execute("ROLLBACK")
            raise
        else:
            self.conn.execute("COMMIT")

    def event(self, event_type: str, payload: Dict[str, Any], task_id: Optional[str] = None, run_id: Optional[str] = None, worker_id: Optional[str] = None) -> None:
        ts = now_iso()
        payload_json = json.dumps(payload, ensure_ascii=False)
        self.conn.execute(
            "INSERT INTO events(ts,event_type,task_id,run_id,worker_id,payload_json) VALUES(?,?,?,?,?,?)",
            (ts, event_type, task_id, run_id, worker_id, payload_json),
        )
        # Keep a human-greppable audit stream beside SQLite. SQLite is the source of
        # truth; JSONL is for fast review and post-mortems.
        append_jsonl(
            self.db_path.parent / "events.jsonl",
            {
                "ts": ts,
                "event_type": event_type,
                "task_id": task_id,
                "run_id": run_id,
                "worker_id": worker_id,
                "payload": payload,
            },
        )

    def reset_graph(self, keep_memory: bool = False, worker_id: str = "system") -> None:
        """Clear task graph/run state before importing a newly generated plan."""
        with self.transaction():
            self.conn.execute("DELETE FROM task_edges")
            self.conn.execute("DELETE FROM task_runs")
            self.conn.execute("DELETE FROM tasks")
            if not keep_memory:
                self.conn.execute("DELETE FROM memory_nodes")
                self.conn.execute("DELETE FROM memory_fts")
            self.event("graph_reset", {"keep_memory": keep_memory}, worker_id=worker_id)

    def upsert_task(self, task: Dict[str, Any], manifest_order: int = 0) -> None:
        ts = now_iso()
        task_id = str(task["id"])
        status = task.get("status") or ("planned" if task_has_gate_specs(task) else "ready")
        if status not in VALID_STATUSES:
            raise ValueError(f"Invalid task status {status!r} for {task_id}")
        next_policy = json.dumps(task.get("next_policy", {}), ensure_ascii=False)
        memory_policy = task.get("memory") if "memory" in task else task.get("memory_policy", {})
        memory_policy_json = json.dumps(memory_policy or {}, ensure_ascii=False)
        verifier_json = json.dumps(task.get("verifier", {}) or {}, ensure_ascii=False)
        task_contract = dict(task.get("contract") or {})
        for _key in ("input_files", "expected_outputs", "done_when", "forbidden", "forbidden_actions", "human_review_required", "permissions", "evidence_files", "artifact_id", "phase", "allowed_write_paths", "review_policy"):
            if _key in task and _key not in task_contract:
                task_contract[_key] = task[_key]
        task_contract_json = json.dumps(task_contract or {}, ensure_ascii=False)
        self.conn.execute(
            """
            INSERT INTO tasks(id,parent_id,title,objective,success_criteria,status,priority,manifest_order,max_attempts,created_by,supersedes,superseded_by,next_policy_json,memory_policy_json,verifier_json,task_contract_json,created_at,updated_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
              parent_id=excluded.parent_id,
              title=excluded.title,
              objective=excluded.objective,
              success_criteria=excluded.success_criteria,
              priority=excluded.priority,
              manifest_order=excluded.manifest_order,
              max_attempts=excluded.max_attempts,
              supersedes=COALESCE(excluded.supersedes, tasks.supersedes),
              superseded_by=COALESCE(excluded.superseded_by, tasks.superseded_by),
              next_policy_json=excluded.next_policy_json,
              memory_policy_json=excluded.memory_policy_json,
              verifier_json=excluded.verifier_json,
              task_contract_json=excluded.task_contract_json,
              updated_at=excluded.updated_at
            """,
            (
                task_id,
                task.get("parent_id"),
                task.get("title", task_id),
                task.get("objective", task.get("title", task_id)),
                task.get("success_criteria", "Worker must produce worker_result.json with status passed and evidence."),
                status,
                int(task.get("priority", 0)),
                manifest_order,
                int(task.get("max_attempts", 3)),
                task.get("created_by", "manifest"),
                task.get("supersedes"),
                task.get("superseded_by"),
                next_policy,
                memory_policy_json,
                verifier_json,
                task_contract_json,
                ts,
                ts,
            ),
        )
        for field, edge_type in EDGE_LIST_FIELDS.items():
            if field in task:
                self.sync_edges(task_id, normalize_string_list(task.get(field, [])), edge_type)
        if "parent_id" in task:
            self.sync_edges(task_id, [str(task["parent_id"])] if task.get("parent_id") else [], "child_of")

    def add_edge(self, from_task: str, to_task: str, edge_type: str) -> None:
        self.conn.execute(
            "INSERT OR IGNORE INTO task_edges(from_task,to_task,edge_type,created_at) VALUES(?,?,?,?)",
            (from_task, to_task, edge_type, now_iso()),
        )

    def sync_edges(self, from_task: str, to_tasks: Iterable[str], edge_type: str) -> None:
        self.conn.execute("DELETE FROM task_edges WHERE from_task=? AND edge_type=?", (from_task, edge_type))
        for to_task in normalize_string_list(to_tasks):
            self.add_edge(from_task, str(to_task), edge_type)

    def get_task(self, task_id: str) -> Optional[sqlite3.Row]:
        return self.conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()

    def list_tasks(self) -> List[sqlite3.Row]:
        return list(self.conn.execute("SELECT * FROM tasks ORDER BY priority DESC, manifest_order ASC, id ASC"))

    def list_runs(self, task_id: Optional[str] = None) -> List[sqlite3.Row]:
        if task_id:
            return list(self.conn.execute("SELECT * FROM task_runs WHERE task_id=? ORDER BY started_at DESC", (task_id,)))
        return list(self.conn.execute("SELECT * FROM task_runs ORDER BY started_at DESC"))

    def list_edges(self, from_task: Optional[str] = None, edge_type: Optional[str] = None) -> List[sqlite3.Row]:
        conditions: List[str] = []
        params: List[Any] = []
        if from_task is not None:
            conditions.append("from_task=?")
            params.append(from_task)
        if edge_type is not None:
            conditions.append("edge_type=?")
            params.append(edge_type)
        where = " WHERE " + " AND ".join(conditions) if conditions else ""
        return list(self.conn.execute(f"SELECT * FROM task_edges{where} ORDER BY from_task, edge_type, to_task", params))

    def get_dependency_tasks(self, task_id: str) -> List[sqlite3.Row]:
        return list(self.conn.execute(
            """
            SELECT d.* FROM task_edges e JOIN tasks d ON d.id=e.to_task
            WHERE e.from_task=? AND e.edge_type='depends_on'
            ORDER BY d.manifest_order, d.id
            """,
            (task_id,),
        ))

    def get_gating_dependency_tasks(self, task_id: str) -> List[sqlite3.Row]:
        placeholders = ",".join("?" for _ in GATING_EDGE_TYPES)
        return list(self.conn.execute(
            f"""
            SELECT d.*, e.edge_type FROM task_edges e JOIN tasks d ON d.id=e.to_task
            WHERE e.from_task=? AND e.edge_type IN ({placeholders})
            ORDER BY e.edge_type, d.manifest_order, d.id
            """,
            [task_id, *sorted(GATING_EDGE_TYPES)],
        ))

    def get_parent_chain(self, task_id: str, max_depth: int = 12) -> List[sqlite3.Row]:
        out: List[sqlite3.Row] = []
        seen = {task_id}
        current = self.get_task(task_id)
        depth = 0
        while current is not None and current["parent_id"] and depth < max_depth:
            parent_id = str(current["parent_id"])
            if parent_id in seen:
                break
            parent = self.get_task(parent_id)
            if parent is None:
                break
            out.append(parent)
            seen.add(parent_id)
            current = parent
            depth += 1
        return out

    def get_same_branch_tasks(self, task_id: str, limit: int = 20) -> List[sqlite3.Row]:
        task = self.get_task(task_id)
        if task is None:
            return []
        parent_id = task["parent_id"] or task_id
        rows = list(self.conn.execute(
            """
            SELECT * FROM tasks
            WHERE (parent_id=? OR id=?) AND id<>?
            ORDER BY updated_at DESC, priority DESC, manifest_order ASC
            LIMIT ?
            """,
            (parent_id, parent_id, task_id, limit),
        ))
        return rows

    def has_gating_edges(self, task_id: str) -> bool:
        placeholders = ",".join("?" for _ in GATING_EDGE_TYPES)
        row = self.conn.execute(
            f"SELECT 1 FROM task_edges WHERE from_task=? AND edge_type IN ({placeholders}) LIMIT 1",
            [task_id, *sorted(GATING_EDGE_TYPES)],
        ).fetchone()
        return row is not None

    def gates_satisfied(self, task_id: str) -> bool:
        placeholders = ",".join("?" for _ in GATING_EDGE_TYPES)
        rows = self.conn.execute(
            f"""
            SELECT e.edge_type, e.to_task AS dep_id, d.id AS existing_id, d.status AS status
            FROM task_edges e LEFT JOIN tasks d ON d.id=e.to_task
            WHERE e.from_task=? AND e.edge_type IN ({placeholders})
            ORDER BY e.edge_type, e.to_task
            """,
            [task_id, *sorted(GATING_EDGE_TYPES)],
        ).fetchall()
        for row in rows:
            if row["existing_id"] is None:
                return False
            edge_type = row["edge_type"]
            status = row["status"]
            if edge_type == "depends_on" and status != "passed":
                return False
            if edge_type == "after_attempt" and status not in TERMINAL_STATUSES:
                return False
            if edge_type == "blocked_by" and status not in {"passed", "skipped", "superseded"}:
                return False
        return True

    def dependencies_passed(self, task_id: str) -> bool:
        """Backward-compatible alias for gate satisfaction."""
        return self.gates_satisfied(task_id)

    def refresh_ready_tasks(self) -> None:
        ts = now_iso()
        expired = self.conn.execute(
            "SELECT id, attempt_count, max_attempts FROM tasks WHERE status='running' AND lease_until IS NOT NULL AND lease_until < ?",
            (ts,),
        ).fetchall()
        for row in expired:
            if int(row["attempt_count"] or 0) >= int(row["max_attempts"] or 1):
                self.conn.execute(
                    """
                    UPDATE tasks
                    SET status='blocked', assigned_worker=NULL, lease_until=NULL,
                        result_summary='Lease expired and max_attempts reached.', updated_at=?
                    WHERE id=?
                    """,
                    (ts, row["id"]),
                )
            else:
                self.conn.execute(
                    "UPDATE tasks SET status='ready', assigned_worker=NULL, lease_until=NULL, updated_at=? WHERE id=?",
                    (ts, row["id"]),
                )
        readyish = self.conn.execute("SELECT id,status FROM tasks WHERE status IN ('planned','blocked')").fetchall()
        for row in readyish:
            task_id = row["id"]
            if row["status"] == "planned" and self.gates_satisfied(task_id):
                self.conn.execute("UPDATE tasks SET status='ready', updated_at=? WHERE id=?", (ts, task_id))
            elif row["status"] == "blocked" and self.has_gating_edges(task_id) and self.gates_satisfied(task_id):
                self.conn.execute("UPDATE tasks SET status='ready', updated_at=? WHERE id=?", (ts, task_id))
        self.conn.execute(
            """
            UPDATE tasks
            SET status='blocked', result_summary='max_attempts reached before claim.', updated_at=?
            WHERE status='ready' AND attempt_count >= max_attempts
            """,
            (ts,),
        )

    def claim_ready_task(self, worker_id: str, lease_seconds: int = 1800) -> Optional[Tuple[sqlite3.Row, str]]:
        with self.transaction():
            self.refresh_ready_tasks()
            task = self.conn.execute(
                "SELECT * FROM tasks WHERE status='ready' ORDER BY priority DESC, manifest_order ASC, id ASC LIMIT 1"
            ).fetchone()
            if not task:
                return None
            attempt = int(task["attempt_count"] or 0) + 1
            run_id = f"R-{now_iso().replace(':','').replace('-','').replace('Z','')}-{uuid.uuid4().hex[:8]}"
            lease_until = None if int(lease_seconds) <= 0 else now_iso_from_seconds(lease_seconds)
            ts = now_iso()
            self.conn.execute(
                "UPDATE tasks SET status='running', assigned_worker=?, lease_until=?, attempt_count=?, updated_at=? WHERE id=?",
                (worker_id, lease_until, attempt, ts, task["id"]),
            )
            self.conn.execute(
                """
                INSERT INTO task_runs(run_id,task_id,attempt,worker_id,status,started_at)
                VALUES(?,?,?,?,?,?)
                """,
                (run_id, task["id"], attempt, worker_id, "running", ts),
            )
            self.event("task_claimed", {"attempt": attempt, "lease_until": lease_until}, task_id=task["id"], run_id=run_id, worker_id=worker_id)
            task = self.get_task(task["id"])
            return task, run_id

    def update_run_paths(self, run_id: str, **paths: str) -> None:
        allowed = {"agent", "prompt_path", "context_path", "memory_selection_path", "transcript_path", "stdout_path", "stderr_path", "result_json_path", "graph_patch_path", "verifier_path"}
        fields = {k: v for k, v in paths.items() if k in allowed}
        if not fields:
            return
        set_sql = ", ".join(f"{k}=?" for k in fields)
        self.conn.execute(f"UPDATE task_runs SET {set_sql} WHERE run_id=?", [*fields.values(), run_id])

    def complete_task_run(self, task_id: str, run_id: str, status: str, summary: str, exit_code: Optional[int] = None) -> None:
        if status not in VALID_STATUSES:
            raise ValueError(f"Invalid completion status {status!r}")
        ts = now_iso()
        with self.transaction():
            self.conn.execute(
                "UPDATE task_runs SET status=?, exit_code=?, ended_at=? WHERE run_id=?",
                (status, exit_code, ts, run_id),
            )
            self.conn.execute(
                "UPDATE tasks SET status=?, result_summary=?, assigned_worker=NULL, lease_until=NULL, updated_at=? WHERE id=?",
                (status, summary, ts, task_id),
            )
            self.event("task_completed", {"status": status, "summary": summary, "exit_code": exit_code}, task_id=task_id, run_id=run_id)
            self.refresh_ready_tasks()

    def get_run(self, run_id: str) -> Optional[sqlite3.Row]:
        return self.conn.execute("SELECT * FROM task_runs WHERE run_id=?", (run_id,)).fetchone()

    def approve_task(self, task_id: str, summary: str = "Human approved.", worker_id: str = "human", require_gates: bool = True) -> None:
        task = self.get_task(task_id)
        if task is None:
            raise KeyError(f"Task not found: {task_id}")
        if require_gates and self.has_gating_edges(task_id) and not self.gates_satisfied(task_id):
            raise ValueError(f"Cannot approve {task_id}: prerequisite gates are not satisfied")
        ts = now_iso()
        with self.transaction():
            self.conn.execute(
                "UPDATE tasks SET status='passed', result_summary=?, assigned_worker=NULL, lease_until=NULL, updated_at=? WHERE id=?",
                (summary, ts, task_id),
            )
            self.event("human_approved_task", {"status": "passed", "summary": summary}, task_id=task_id, worker_id=worker_id)
            self.refresh_ready_tasks()

    def reject_task(self, task_id: str, summary: str = "Human rejected; blocked for revision.", worker_id: str = "human") -> None:
        task = self.get_task(task_id)
        if task is None:
            raise KeyError(f"Task not found: {task_id}")
        ts = now_iso()
        with self.transaction():
            self.conn.execute(
                "UPDATE tasks SET status='blocked', result_summary=?, assigned_worker=NULL, lease_until=NULL, updated_at=? WHERE id=?",
                (summary, ts, task_id),
            )
            self.event("human_rejected_task", {"status": "blocked", "summary": summary}, task_id=task_id, worker_id=worker_id)
            self.refresh_ready_tasks()

    def add_memory_node(self, node: Dict[str, Any]) -> None:
        ts = now_iso()
        node_id = node["id"]
        tags = normalize_string_list(node.get("tags", []))
        tags_json = json.dumps(tags, ensure_ascii=False)
        raw_json = json.dumps(node.get("raw_artifacts", []), ensure_ascii=False)
        self.conn.execute(
            """
            INSERT OR REPLACE INTO memory_nodes(id,task_id,run_id,scope,tags_json,title,node_dir,content,raw_artifacts_json,confidence,status,superseded_by,created_at,updated_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                node_id,
                node.get("task_id"),
                node.get("run_id"),
                node.get("scope", "task"),
                tags_json,
                node.get("title", node_id),
                node.get("node_dir", ""),
                node.get("content", ""),
                raw_json,
                float(node.get("confidence", 0.7)),
                node.get("status", "active"),
                node.get("superseded_by"),
                node.get("created_at", ts),
                ts,
            ),
        )
        self.conn.execute("DELETE FROM memory_fts WHERE id=?", (node_id,))
        self.conn.execute(
            "INSERT INTO memory_fts(id,title,scope,tags,content) VALUES(?,?,?,?,?)",
            (node_id, node.get("title", node_id), node.get("scope", "task"), " ".join(tags), node.get("content", "")),
        )

    def list_memory(self, limit: int = 20) -> List[sqlite3.Row]:
        return list(self.conn.execute("SELECT * FROM memory_nodes WHERE status='active' ORDER BY updated_at DESC LIMIT ?", (limit,)))

    def get_memory_by_ids(self, memory_ids: Iterable[str]) -> List[sqlite3.Row]:
        ids = [str(x) for x in memory_ids if str(x)]
        if not ids:
            return []
        placeholders = ",".join("?" for _ in ids)
        rows = list(self.conn.execute(f"SELECT * FROM memory_nodes WHERE id IN ({placeholders}) AND status='active'", ids))
        by_id = {r["id"]: r for r in rows}
        return [by_id[i] for i in ids if i in by_id]

    def list_memory_for_task_ids(self, task_ids: Iterable[str], limit: int = 50) -> List[sqlite3.Row]:
        ids = [str(x) for x in task_ids if str(x)]
        if not ids:
            return []
        placeholders = ",".join("?" for _ in ids)
        return list(self.conn.execute(
            f"""
            SELECT * FROM memory_nodes
            WHERE status='active' AND task_id IN ({placeholders})
            ORDER BY updated_at DESC, id ASC
            LIMIT ?
            """,
            [*ids, int(limit)],
        ))

    def list_memory_by_tags_scopes(self, tags: Iterable[str] = (), scopes: Iterable[str] = (), limit: int = 50, match_mode: str = "any") -> List[sqlite3.Row]:
        tag_list = normalize_string_list(tags)
        scope_list = normalize_string_list(scopes)
        if not tag_list and not scope_list:
            return []
        conditions: List[str] = []
        params: List[Any] = []
        if tag_list:
            tag_clauses = []
            for tag in tag_list:
                tag_clauses.append("tags_json LIKE ?")
                params.append(f'%"{tag}"%')
            joiner = " AND " if match_mode == "all" else " OR "
            conditions.append("(" + joiner.join(tag_clauses) + ")")
        if scope_list:
            placeholders = ",".join("?" for _ in scope_list)
            conditions.append(f"scope IN ({placeholders})")
            params.extend(scope_list)
        sql = "SELECT * FROM memory_nodes WHERE status='active' AND (" + " OR ".join(conditions) + ") ORDER BY updated_at DESC, id ASC LIMIT ?"
        params.append(int(limit))
        return list(self.conn.execute(sql, params))

    def search_memory(self, query: str, limit: int = 10) -> List[sqlite3.Row]:
        if not query.strip():
            return self.list_memory(limit)
        fts_query = make_fts_query(query)
        if fts_query:
            try:
                return list(self.conn.execute(
                    """
                    SELECT m.*, bm25(memory_fts) AS rank
                    FROM memory_fts JOIN memory_nodes m ON m.id=memory_fts.id
                    WHERE memory_fts MATCH ? AND m.status='active'
                    ORDER BY rank LIMIT ?
                    """,
                    (fts_query, limit),
                ))
            except sqlite3.OperationalError:
                pass
        like = f"%{query[:160]}%"
        return list(self.conn.execute(
            "SELECT * FROM memory_nodes WHERE status='active' AND (title LIKE ? OR content LIKE ? OR tags_json LIKE ?) ORDER BY updated_at DESC LIMIT ?",
            (like, like, like, limit),
        ))

    def apply_graph_operation(self, op: Dict[str, Any]) -> None:
        kind = op.get("op")
        if kind == "add_task":
            task = dict(op["task"])
            if "status" not in task:
                task["status"] = "planned" if task_has_gate_specs(task) else "ready"
            order = int(task.get("manifest_order", 10_000))
            self.upsert_task(task, order)
        elif kind == "update_task":
            task_id = op["id"]
            fields = dict(op.get("fields", {}))
            edge_updates: Dict[str, List[str]] = {}
            for field, edge_type in EDGE_LIST_FIELDS.items():
                if field in fields:
                    edge_updates[edge_type] = normalize_string_list(fields.pop(field))
            if "memory" in fields:
                fields["memory_policy_json"] = json.dumps(fields.pop("memory") or {}, ensure_ascii=False)
            if "memory_policy" in fields:
                fields["memory_policy_json"] = json.dumps(fields.pop("memory_policy") or {}, ensure_ascii=False)
            if "next_policy" in fields:
                fields["next_policy_json"] = json.dumps(fields.pop("next_policy") or {}, ensure_ascii=False)
            if "verifier" in fields:
                fields["verifier_json"] = json.dumps(fields.pop("verifier") or {}, ensure_ascii=False)
            if "contract" in fields:
                fields["task_contract_json"] = json.dumps(fields.pop("contract") or {}, ensure_ascii=False)
            contract_update = {}
            for _key in ("input_files", "expected_outputs", "done_when", "forbidden", "forbidden_actions", "human_review_required", "permissions", "evidence_files", "artifact_id", "phase", "allowed_write_paths", "review_policy"):
                if _key in fields:
                    contract_update[_key] = fields.pop(_key)
            if contract_update:
                existing = self.get_task(task_id)
                base_contract = {}
                if existing is not None:
                    try:
                        base_contract = json.loads(existing["task_contract_json"] or "{}")
                    except Exception:
                        base_contract = {}
                base_contract.update(contract_update)
                fields["task_contract_json"] = json.dumps(base_contract, ensure_ascii=False)
            allowed = {
                "parent_id", "title", "objective", "success_criteria", "status", "priority", "max_attempts",
                "result_summary", "next_policy_json", "memory_policy_json", "verifier_json", "task_contract_json", "supersedes", "superseded_by",
            }
            updates = {k: v for k, v in fields.items() if k in allowed}
            if "status" in updates and updates["status"] not in VALID_STATUSES:
                raise ValueError(f"Invalid status in patch for {task_id}: {updates['status']}")
            if updates:
                updates["updated_at"] = now_iso()
                set_sql = ", ".join(f"{k}=?" for k in updates)
                self.conn.execute(f"UPDATE tasks SET {set_sql} WHERE id=?", [*updates.values(), task_id])
            for edge_type, to_tasks in edge_updates.items():
                self.sync_edges(task_id, to_tasks, edge_type)
        elif kind == "add_edge":
            self.add_edge(op["from_task"], op["to_task"], op.get("edge_type", "depends_on"))
        elif kind == "remove_edge":
            self.conn.execute(
                "DELETE FROM task_edges WHERE from_task=? AND to_task=? AND edge_type=?",
                (op["from_task"], op["to_task"], op.get("edge_type", "depends_on")),
            )
        elif kind == "supersede_task":
            old_id = op["old_id"]
            new_task = dict(op["new_task"])
            new_id = new_task["id"]
            new_task["supersedes"] = old_id
            self.upsert_task(new_task, int(new_task.get("manifest_order", 10_000)))
            ts = now_iso()
            self.conn.execute("UPDATE tasks SET status='superseded', superseded_by=?, updated_at=? WHERE id=?", (new_id, ts, old_id))
            self.conn.execute("UPDATE tasks SET supersedes=?, updated_at=? WHERE id=?", (old_id, ts, new_id))
        elif kind == "supersede_memory":
            old_id = op["old_id"]
            new_id = op.get("new_id") or op.get("superseded_by")
            self.conn.execute("UPDATE memory_nodes SET status='superseded', superseded_by=?, updated_at=? WHERE id=?", (new_id, now_iso(), old_id))
        else:
            raise ValueError(f"Unsupported graph patch operation: {kind!r}")


def task_has_gate_specs(task: Dict[str, Any]) -> bool:
    for field, edge_type in EDGE_LIST_FIELDS.items():
        if edge_type in GATING_EDGE_TYPES and normalize_string_list(task.get(field, [])):
            return True
    return False


def normalize_string_list(items: Iterable[Any] | Any) -> List[str]:
    if items is None:
        return []
    if isinstance(items, str):
        items = [items]
    out: List[str] = []
    for item in items or []:
        s = str(item).strip()
        if s and s not in out:
            out.append(s)
    return out


def make_fts_query(query: str, max_terms: int = 32) -> str:
    # Avoid feeding arbitrary punctuation into FTS MATCH. This is deliberately simple and stable.
    tokens = re.findall(r"[A-Za-z0-9_./:-]+|[\u4e00-\u9fff]+", query)
    cleaned: List[str] = []
    for token in tokens:
        token = token.strip().strip("'\"")
        if len(token) < 2:
            continue
        if token not in cleaned:
            cleaned.append(token)
        if len(cleaned) >= max_terms:
            break
    return " OR ".join('"' + t.replace('"', '') + '"' for t in cleaned)


def now_iso_from_seconds(seconds: int) -> str:
    from datetime import datetime, timedelta, timezone

    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
