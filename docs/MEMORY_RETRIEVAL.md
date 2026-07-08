# Memory retrieval in v0.7.0

Memory is non-lossy: raw evidence remains in `runs/` and `memory/nodes/`. Summaries and excerpts are indexes, not substitutes for raw records.

Default policy:

```yaml
memory:
  inject_full_nodes: false
  node_excerpt_lines: 80
  include_raw_artifact_paths: true
  max_nodes_total: 24
  max_context_chars: 120000
```

Retrieval order:

1. explicit required memory ids
2. previous attempts of the same task
3. parent task chain
4. gate memory from `depends_on`, `after_attempt`, and `blocked_by`
5. explicit required task ids
6. recent same-branch task memory
7. required tags/scopes
8. explicit search queries
9. automatic FTS from task text

Preview:

```bash
python -m autopilot_nodekit memory-plan --workspace . --task-id F001_RENDER
```
