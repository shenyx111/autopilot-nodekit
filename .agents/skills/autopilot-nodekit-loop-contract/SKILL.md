---
name: autopilot-nodekit-loop-contract
description: Use when turning a vague Codex coding, debugging, CI, benchmarking, reproduction, or experiment task into a bounded Autopilot NodeKit loop with a verifier, state file, graph semantics, and stop conditions.
---

# Autopilot NodeKit Loop Contract

Use this skill before long-running debugging, refactoring, benchmarking, reproduction, CI-fix, research-code, or experiment-automation tasks. For large artifact batches such as journal figures, switch to `$autopilot-review-gated-figure-loop` and enforce human plan review, boundary test, pilot review, and final audit gates.

## 1. Define the loop before editing

Write a short loop contract with:

- Codex `/goal`: render it with `python -m autopilot_nodekit codex-goal --workspace . --task-id <ID>` when the task maps to a NodeKit task.
- Goal: the concrete outcome.
- Scope: files, modules, datasets, or issues included.
- Non-goals: what must not be changed.
- State file: `LOOP_STATE.md` or `PLANS.md`.
- Verifier: exact command, test, benchmark, or artifact check.
- Max iterations: default 3 unless the user asks otherwise.
- Stop condition: success, blocker, repeated failure with no new hypothesis, or scope risk.

## 2. Use NodeKit as outer loop

Autopilot NodeKit is authoritative for task state. Do not bypass it by manually editing `automation/autopilot.sqlite`.

When working inside a claimed task, read:

- `$AUTOPILOT_PROMPT`
- `$AUTOPILOT_CONTEXT_PACK`
- `$AUTOPILOT_VERIFIER_COMMAND`

## 3. Make verifier authoritative

Do not write `status: passed` unless the verifier is expected to pass.

If the verifier fails, write `status: failed` or `blocked` and include evidence from logs.

## 4. Apply graph semantics correctly

Use:

- `depends_on` only when the predecessor must be `passed`.
- `after_attempt` for bridge tasks that should run after a predecessor finishes, even if it failed.
- `blocked_by` for explicit blockers that release after passed/skipped/superseded.
- `parent_id` for lineage.
- `memory.required_task_ids` to force memory inheritance from failed or blocked tasks.

## 5. Iterate safely

For each iteration:

1. Read current state and memory.
2. Choose the smallest defensible next action.
3. Make the patch.
4. Run the verifier or explain why it cannot run.
5. Update `LOOP_STATE.md` / `PLANS.md`.
6. Write `worker_result.json` with status, summary, details, memory nodes, and any graph patch.

## 6. Final result contract

The final worker result must contain:

- status: `passed`, `failed`, `blocked`, or `skipped`
- summary: one-line manifest result
- details: evidence-rich explanation
- memory_nodes: reusable facts, commands, decisions, failures, and artifact paths
- graph_patch: only if the task graph should change
