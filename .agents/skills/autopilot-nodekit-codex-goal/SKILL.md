---
name: autopilot-nodekit-codex-goal
description: Use when setting or refining a native Codex /goal for an Autopilot NodeKit task, especially to keep the goal under Codex limits while preserving verifier, scope, memory, and stop-condition semantics.
---

# Autopilot NodeKit Codex Goal

Codex owns native `/goal` state in the active Codex thread. NodeKit owns durable external state: task graph, verifier, run artifacts, and memory nodes.

## Goal rendering

Prefer rendering a task-specific goal:

```bash
python -m autopilot_nodekit codex-goal --workspace . --task-id <TASK_ID>
```

Paste the result into Codex CLI/app/IDE.

## Goal requirements

A NodeKit-compatible `/goal` must include:

- task id and objective
- success criteria
- verifier command or first action to define one
- allowed scope and graph safety rules
- memory/state files: `AGENTS.md`, `LOOP_STATE.md`, `PLANS.md`, `automation/manifest.yml`
- iteration rule
- stop condition

## Important distinction

Do not assume `codex exec` attaches a durable `/goal` to the active interactive thread. Use `/goal` in Codex itself for native Goal mode, then use NodeKit commands as the controlled outer loop.
