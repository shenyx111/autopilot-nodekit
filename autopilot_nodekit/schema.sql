PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS tasks (
  id TEXT PRIMARY KEY,
  parent_id TEXT,
  title TEXT NOT NULL,
  objective TEXT NOT NULL,
  success_criteria TEXT NOT NULL,
  status TEXT NOT NULL,
  priority INTEGER DEFAULT 0,
  manifest_order INTEGER DEFAULT 0,
  attempt_count INTEGER DEFAULT 0,
  max_attempts INTEGER DEFAULT 3,
  assigned_worker TEXT,
  lease_until TEXT,
  created_by TEXT DEFAULT 'manifest',
  supersedes TEXT,
  superseded_by TEXT,
  result_summary TEXT,
  next_policy_json TEXT,
  memory_policy_json TEXT,
  verifier_json TEXT,
  task_contract_json TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS task_edges (
  from_task TEXT NOT NULL,
  to_task TEXT NOT NULL,
  edge_type TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY (from_task, to_task, edge_type)
);

CREATE TABLE IF NOT EXISTS task_runs (
  run_id TEXT PRIMARY KEY,
  task_id TEXT NOT NULL,
  attempt INTEGER NOT NULL,
  worker_id TEXT NOT NULL,
  agent TEXT,
  status TEXT NOT NULL,
  exit_code INTEGER,
  prompt_path TEXT,
  context_path TEXT,
  memory_selection_path TEXT,
  transcript_path TEXT,
  stdout_path TEXT,
  stderr_path TEXT,
  result_json_path TEXT,
  graph_patch_path TEXT,
  verifier_path TEXT,
  started_at TEXT NOT NULL,
  ended_at TEXT
);

CREATE TABLE IF NOT EXISTS memory_nodes (
  id TEXT PRIMARY KEY,
  task_id TEXT,
  run_id TEXT,
  scope TEXT NOT NULL,
  tags_json TEXT NOT NULL,
  title TEXT NOT NULL,
  node_dir TEXT NOT NULL,
  content TEXT NOT NULL,
  raw_artifacts_json TEXT NOT NULL,
  confidence REAL DEFAULT 0.7,
  status TEXT DEFAULT 'active',
  superseded_by TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(
  id UNINDEXED,
  title,
  scope,
  tags,
  content
);

CREATE TABLE IF NOT EXISTS events (
  event_id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL,
  event_type TEXT NOT NULL,
  task_id TEXT,
  run_id TEXT,
  worker_id TEXT,
  payload_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status, priority, manifest_order);
CREATE INDEX IF NOT EXISTS idx_edges_from ON task_edges(from_task, edge_type);
CREATE INDEX IF NOT EXISTS idx_edges_to ON task_edges(to_task, edge_type);
CREATE INDEX IF NOT EXISTS idx_runs_task ON task_runs(task_id, attempt);
CREATE INDEX IF NOT EXISTS idx_memory_task ON memory_nodes(task_id, run_id);
CREATE INDEX IF NOT EXISTS idx_memory_status ON memory_nodes(status, updated_at);
