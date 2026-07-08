---
name: autopilot-nodekit-memory-curator
description: Use when creating, selecting, or reviewing Autopilot NodeKit structured memory nodes so future Codex runs inherit durable evidence without bloating prompt context.
---

# Autopilot NodeKit Memory Curator

Structured memory nodes are durable evidence pointers, not compressed chat summaries.

## What belongs in memory

Create nodes for:

- exact commands and environment assumptions
- reproducible bugs and root causes
- API, schema, and file contracts
- decisions that affect future tasks
- verifier evidence and artifact paths

Avoid nodes for:

- generic commentary
- unverified guesses
- facts not useful to future tasks

## Non-lossy retrieval pattern

Keep the raw evidence in `runs/<run_id>/` and `memory/nodes/<node_id>/`.

Prompt context should usually receive excerpts plus `node_file` and `raw_artifacts`, not every full node body.

## Future-use cues

Every node should make clear when a future task should load it, what raw artifact to inspect, and what confidence to assign.
