---
name: autopilot-nodekit-graph-curator
description: Use when reviewing, repairing, or designing Autopilot NodeKit task graphs, including depends_on, after_attempt, blocked_by, supersede_task, and memory inheritance selectors.
---

# Autopilot NodeKit Graph Curator

Use this skill to keep the task graph executable and auditable.

## Edge semantics

- `depends_on`: predecessor must be `passed`.
- `after_attempt`: predecessor must reach any terminal status: `passed`, `failed`, `blocked`, `skipped`, or `superseded`.
- `blocked_by`: predecessor releases this task only after `passed`, `skipped`, or `superseded`.
- `child_of`: lineage only, not a readiness gate.
- `inserted_before`: planning/order hint only, not a readiness gate.
- `supersedes`: history link only, not a readiness gate.

## Bridge task pattern

When task `T001` fails because setup is unknown:

- Insert `T001.1` with `parent_id: T001` and `after_attempt: [T001]`.
- Add `memory.required_task_ids: [T001]`.
- Do not use `depends_on: [T001]` unless `T001` passed.

## Validation checklist

Run:

```bash
python -m autopilot_nodekit validate --workspace .
```

Then check:

- no dangling edges
- no gating cycles
- no planned task waiting forever on a failed `depends_on`
- future tasks have memory selectors for bridge outputs
