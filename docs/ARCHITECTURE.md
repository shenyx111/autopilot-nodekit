# Architecture

Autopilot NodeKit is a local control plane for long-running agents.

```text
manifest.yml
  ↓ import
SQLite task graph
  ↓ claim ready task
context builder
  ↓ deterministic memory retrieval
runs/<run_id>/prompt.md + context_pack.json
  ↓ worker command in shell/tmux/Codex/Claude/Aider
worker_result.json
  ↓
memory node creation + graph_patch application
  ↓
manifest.live.md / manifest.live.tsv
```

## Responsibilities

The control plane owns:

- task state
- atomic claiming and leases
- task graph edges
- memory indexing and deterministic retrieval
- run directories and raw evidence
- live manifest rendering
- append-only events

The worker owns:

- solving the claimed task
- producing `worker_result.json`
- proposing `graph_patch` operations
- writing memory nodes in the result contract

Workers should not edit SQLite directly.

## Why SQLite

SQLite WAL gives a reliable local source of truth and simple atomic claiming. It is easier to inspect and migrate than a hidden agent memory store. Markdown and TSV files are generated views for humans, not the canonical database.

## Why deterministic memory before search

Task chains such as `T001 → T001.1 → T002@v2` carry causal information. That information should be loaded because of graph structure, not because a keyword happens to match.
