# Memory Node Design

Autopilot NodeKit uses structured, non-lossy memory nodes.

A memory node is not a lossy summary. It is a curated Markdown file plus metadata that points back to raw evidence.

```text
runs/<run_id>/
  prompt.md
  context_pack.json
  stdout.log
  stderr.log
  transcript.log
  verifier.log
  worker_result.json
  graph_patch.json

memory/nodes/<node_id>/
  node.md
  metadata.json
```

## What belongs in `node.md`

Each node should include:

- exact commands
- exact files/modules touched
- failure signatures and error messages
- decision rationale
- assumptions discovered or invalidated
- raw artifact paths
- next-use cues

## What should not happen

Do not overwrite old nodes after contradictions. Create a new node and mark the old node superseded in metadata/DB. This preserves the historical path that led to task graph changes.

## Retrieval

v0.3 retrieves nodes by task graph links and explicit memory selectors first. A future task can explicitly require memory from previous tasks:

```yaml
memory:
  required_task_ids: [T001, T001.1]
  required_tags: [setup, pytest]
  required_scopes: [tool, bug, decision]
```

The generated `prompt.md` lists the injected nodes and the reasons they were selected.
