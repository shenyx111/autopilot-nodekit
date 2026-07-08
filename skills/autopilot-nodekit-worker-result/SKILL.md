---
name: autopilot-nodekit-worker-result
description: Use when writing or reviewing Autopilot NodeKit worker_result.json files, especially to ensure status, verifier evidence, memory nodes, and graph_patch operations are valid.
---

# Autopilot NodeKit Worker Result Contract

A worker must write `$AUTOPILOT_RUN_DIR/worker_result.json` before exiting.

## Required fields

```json
{
  "status": "passed | failed | blocked | skipped",
  "summary": "One-line result for manifest.live.",
  "details": "Full evidence and decisions.",
  "memory_nodes": []
}
```

## Status rules

- `passed`: success criteria satisfied and verifier expected to pass.
- `failed`: attempted work did not satisfy criteria or verifier failed.
- `blocked`: missing input, missing dependency, environment failure, or unsafe next step.
- `skipped`: intentionally not needed, with evidence.

The verifier is authoritative. A pass-like result will be overridden by NodeKit if the worker command or verifier exits non-zero.

## Memory node rules

Create memory nodes for reusable facts:

- exact setup/test/build commands
- failure modes and root causes
- file/module decisions
- API or schema contracts
- blocker evidence

Each node should include `title`, `scope`, `tags`, `content`, `raw_artifacts`, and `confidence`.

## Graph patch rules

Use `graph_patch.operations` for durable task graph changes.

For bridge tasks after a failed parent, do this:

```json
{
  "op": "add_task",
  "task": {
    "id": "T001.1",
    "parent_id": "T001",
    "after_attempt": ["T001"],
    "memory": {"required_task_ids": ["T001"]}
  }
}
```

Do not put `depends_on: ["T001"]` on a bridge that should run after `T001` fails.
