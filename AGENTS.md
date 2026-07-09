# AGENTS.md

## Project identity

This repository is a Codex-native local autopilot control plane.

Use Autopilot NodeKit as the outer loop. Do not create independent unbounded inner loops unless the task explicitly asks for them.

## Core commands

- Install: `python -m pip install -e .`
- Demo: `make demo`
- Compile check: `python -m compileall -q autopilot_nodekit`
- Tests: `python -m pytest -q`
- Status: `python -m autopilot_nodekit status --workspace .`
- Validate graph: `python -m autopilot_nodekit validate --workspace .`
- Codex-native files: `python -m autopilot_nodekit install-codex-native --workspace .`
- Generate a native goal: `python -m autopilot_nodekit codex-goal --workspace . --task-id T001`
- Preferred prompt-to-loop startup: `python -m autopilot_nodekit start-from-prompt --workspace . --prompt-file PROJECT_PROMPT.md --gate-mode fast --force-codex-native`
- AI draft/refine project spec: `python -m autopilot_nodekit codex-draft-spec --workspace . --prompt-file PROJECT_PROMPT.md --gate-mode fast`
- Start from an explicit spec: `python -m autopilot_nodekit start-from-spec --workspace . --spec PROJECT_SPEC.yml --force-codex-native`
- Legacy strict figure startup: `python -m autopilot_nodekit start-figures --workspace . --figures 100 --journal "target journal" --gate-mode strict`
- Review Layer 0 setup: read `PROJECT_SETUP.yml` and `SETUP_REVIEW.md`.
- Approve setup after human review: `python -m autopilot_nodekit approve-setup --workspace .`
- Review plan: read `GOAL_CONTRACT.md`, `TASK_REVIEW.md`, `REQUIREMENTS_LOCK.md`, and `automation/manifest.live.md`.
- Approve plan after human review: `python -m autopilot_nodekit approve-plan --workspace .`
- Prepare one interactive Codex task dialog: `python -m autopilot_nodekit codex-prepare --workspace . --worker-id codex-interactive`
- Finish an interactive Codex task after `worker_result.json` exists: `python -m autopilot_nodekit codex-finish --workspace . --run-id <run_id>`
- Run non-interactive loop: `python -m autopilot_nodekit worker-loop --workspace . --worker-id codex-local`

## Non-negotiable loop workflow

Prefer PROJECT_SPEC-driven startup. A fuzzy user prompt should be converted into `PROJECT_SPEC.yml`, then into `PROJECT_SETUP.yml`, `GOAL_CONTRACT.yml`, and `automation/manifest.yml`.

Gate modes control how often humans stop the loop:

- `fast`: one startup review, then boundary test, F001 automatic pilot guard, bulk loop, final audit.
- `balanced`: one startup review, boundary test, F001 human pilot review, bulk loop, final audit.
- `strict`: separate setup review, plan review, boundary test, F001 human pilot review, bulk loop, final audit.

Do not collapse a large artifact request into a tiny task list. For `N` figures/artifacts, the graph must contain at least `N` tasks and normally at least `2N`; with 100 figures and 3 tasks per figure, fast mode creates 303 tasks, balanced 304, and strict 305.

## Hard gate rules

- In fast/balanced mode, `G000_START_REVIEW` starts as `review_pending` and is not claimable by workers; approve it with `approve-start` only after reading `PROJECT_SPEC.md`, `SETUP_REVIEW.md`, `GOAL_CONTRACT.md`, `TASK_REVIEW.md`, and `REQUIREMENTS_LOCK.md`.
- In strict mode, `G000_SETUP_REVIEW` and `H000_PLAN_REVIEW` are separate `review_pending` gates.
- `H010_BOUNDARY_PERMISSION_TEST` must depend on the approved startup/plan gate and must pass before figure work.
- In fast mode, `F002+` bulk figure tasks must depend on `F001_QC`; this is the automatic pilot guard with no extra human stop.
- In balanced/strict mode, `H020_PILOT_REVIEW` starts as `review_pending`, depends on `F001_QC`, and gates `F002+`.
- `Z999_FINAL_AUDIT` must depend on all figure QC tasks.
- Approvals must use `approve-start`, `approve-setup`, `approve-plan`, `approve-pilot`, or `approve-task`; do not edit SQLite manually.
- Run `python -m autopilot_nodekit validate --workspace . --strict` after graph generation, approvals, graph patches, and before bulk work.

## Safety rules

- Do not mark a task passed unless the configured verifier passes.
- Treat verifier output as more authoritative than the worker's self-reported status.
- Every non-human task pass requires Santa dual-review: two independent reviewers must return NICE/NICE in `worker_result.json`.
- If either reviewer returns NAUGHTY, repair the smallest issue, re-run the verifier, and re-run fresh reviews.
- Do not edit `automation/autopilot.sqlite` directly.
- Do not delete task history; supersede instead.
- Treat `runs/` and `memory/nodes/` as durable evidence.
- If `worker_result.json` is malformed, mark the run failed and preserve the malformed file.
- If the next action would bypass a human gate, stop and report the gate that needs approval.

## Graph rules

- Use `depends_on` only for dependencies that must be `passed`.
- Use `after_attempt` for diagnostic bridge tasks that should run after a failed, blocked, skipped, superseded, or passed predecessor.
- Use `blocked_by` only for explicit blockers that should release after passed/skipped/superseded.
- Use `parent_id` and `memory.required_task_ids` to inherit context from a failed parent.
- Run `python -m autopilot_nodekit validate --workspace .` after graph patches.

## Codex loop rules

For debugging, refactoring, benchmarking, reproduction, CI-fix, experiment, or artifact-batch tasks that may require multiple attempts, use `$autopilot-nodekit-loop-contract`. For prompt-to-spec startup, use `$autopilot-project-spec`. For journal figures or similar artifact batches, use `$autopilot-review-gated-figure-loop`. For per-task adversarial review, use `$autopilot-santa-review`.

Use `python -m autopilot_nodekit codex-goal --workspace . --task-id <ID>` to render a pasteable Codex `/goal` command for a NodeKit task. Codex owns durable `/goal` state inside the active Codex thread; NodeKit owns the external task graph, verifier, review gates, and evidence trail.

For an interactive per-task Codex dialog:

1. `python -m autopilot_nodekit codex-prepare --workspace . --worker-id codex-interactive`
2. Run the printed `bash runs/<run_id>/open_codex.sh` command.
3. Let Codex complete that one task and write `runs/<run_id>/worker_result.json`.
4. `python -m autopilot_nodekit codex-finish --workspace . --run-id <run_id>`.

Keep progress in `LOOP_STATE.md` or `PLANS.md`. Do not declare success without verifier evidence. If `/goal` is hidden, enable `features.goals = true` in `.codex/config.toml` or run `codex features enable goals`.


## v0.8 Smart-start trigger rule

If the user says any of the following, treat it as an automatic trigger for Autopilot NodeKit startup, even if their prompt is short:

- "基于 autopilot-nodekit"
- "use autopilot-nodekit"
- "autopilot-nodekit"
- "NodeKit loop"

Do not ask the user to paste the long control-plane prompt. The fixed flow is now built into this package.

Required first action:

```bash
python -m autopilot_nodekit smart-start --workspace . --prompt-file PROJECT_PROMPT.md --force-codex-native
```

If the user has not yet created `PROJECT_PROMPT.md`, create it from the user's latest natural-language request first, then run `smart-start`.

`smart-start` must ask before execution when any required startup setting is missing:

- `gate_mode`: `fast`, `balanced`, or `strict`
- `task_scale`: `smoke`, `standard`, or `prod`
- `artifact_count`
- `target_journal` / target venue for figure projects
- generated deliverables if the requested output files are unclear

Do not silently default `gate_mode` or `task_scale` in the fixed smart-start flow. If these settings are unclear, write/read `START_QUESTIONS.md` and wait for user answers.

Task scale controls graph density:

- `smoke`: 2 tasks/artifact, intended for quick verification and still at least one task per artifact.
- `standard`: 3 tasks/artifact, the default production balance.
- `prod`: 4 tasks/artifact with a separate journal/compliance check.

Background execution must use backend detection instead of assuming tmux:

```bash
python -m autopilot_nodekit background-doctor --workspace .
python -m autopilot_nodekit launch-background --workspace . --worker-id codex-worker --max-cycles 0
```

`--max-cycles 0` means no NodeKit cycle limit. NodeKit defaults do not impose wall-clock timeouts on background worker/verifier commands.

Layer commands:

- Goal/contract: `project-spec-review`, `contract-review`, `codex-contract-goal`
- Task manifest/DAG: `review-plan`, `validate --strict`, `status`
- Execution loop: `codex-prepare`, run `runs/<run_id>/open_codex.sh`, `codex-finish`
- Memory/state: `memory-plan`, `memory-search`, `replay-run`
- Verification: `verify-artifact`, `validate --strict`, verifier logs in `runs/<run_id>/verifier.log`
- Repair: `add-repair-task`, then `codex-prepare` and `codex-finish`
- Human gate: `approve-start`, `approve-setup`, `approve-plan`, `approve-pilot`, `approve-task`, `reject-task`
- Observability: `metrics`, `replay-run`, `automation/events.jsonl`, `automation/manifest.live.md`


## v0.9 Bootstrap hardening rules

Before approving startup or launching unattended background workers, run:

```bash
python -m autopilot_nodekit background-doctor --workspace .
python -m autopilot_nodekit validate --workspace . --strict
```

Do not approve startup if bootstrap checks show any of these unresolved problems:

- `worker.command` is empty;
- `autopilot_nodekit` cannot be imported from the workspace/background environment;
- `.codex/config.toml` contains `job_max_runtime_seconds = 0`;
- Windows hooks contain `/bin/sh`;
- requested tmux backend fails a real tmux smoke test;
- a running task has no live heartbeat and no worker_result.

Use `.nodekit/nodekit` and `.nodekit/codex_worker.*` wrappers instead of relying on ad hoc shell PYTHONPATH.

For non-figure science workflows, do not let demo/figure templates drive the project. Prefer an explicit `PROJECT_SPEC.yml` with `project.type` such as `science_workflow`, `materials_dft_sevennet`, `matlantis_workflow`, or `rag_local_llm`, then run `start-from-spec`.

When a repair task passes, use `resolve-by-repair` if the failed parent blocks downstream tasks. Do not keep nesting repair tasks forever.

For detached/background runs, do not mechanically run `codex-finish` while the child worker may still be alive. Use `background-status`, `events.jsonl`, heartbeat files, and `recover-stale` if the run is abandoned.
