# Review-gated workflow

This workflow is for repeated deliverables such as publication-ready figures, simulation batches, data pipelines, and long code-repair loops.

## Recommended fast gate order

```text
G000_START_REVIEW
  ↓
H010_BOUNDARY_PERMISSION_TEST
  ↓
F001_SPEC -> F001_RENDER -> F001_QC
  ↓
F002+ bulk tasks
  ↓
Z999_FINAL_AUDIT
```

Fast mode has one initial human gate, then relies on verifiers, repair tasks, operator automation, evidence logs, metrics, and final audit. In v0.9.3, routine repair / recover / resolve transitions should be handled by the background worker and operator, not by asking the user to press `next-command` after every step.

## Balanced and strict modes

```text
balanced: G000_START_REVIEW -> boundary test -> F001 pilot -> H020_PILOT_REVIEW -> bulk loop -> final audit
strict:   G000_SETUP_REVIEW -> H000_PLAN_REVIEW -> boundary test -> F001 pilot -> H020_PILOT_REVIEW -> bulk loop -> final audit
```

## Operator-first command sequence

```bash
python -m autopilot_nodekit smart-start --workspace . --prompt-file PROJECT_PROMPT.md --force-codex-native
python -m autopilot_nodekit approve-start --workspace . --summary "Spec, setup, permissions, task DAG, and loop mode reviewed."
python -m autopilot_nodekit background-doctor --workspace .
python -m autopilot_nodekit launch-background --workspace . --worker-id codex-worker --max-cycles 0
```

`next-command` remains useful for diagnosis and supervision. It should not be the normal button the user presses after every routine repair.

## Non-human completion rule

A non-human task cannot pass unless:

1. the worker result says `passed`;
2. the configured verifier succeeds, if present;
3. Santa reviewer A returns `NICE` with evidence, when the task requires Santa review;
4. Santa reviewer B returns `NICE` with evidence, when the task requires Santa review.

If these checks fail, NodeKit records the failure and repair/operator logic handles the next safe control-plane step.
