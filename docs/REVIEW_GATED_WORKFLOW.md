# Review-gated workflow in v0.7.0

This workflow is for large repeated deliverables such as 100 publication-ready journal figures.

## Recommended fast gate order

```text
G000_START_REVIEW
  ↓
H010_BOUNDARY_PERMISSION_TEST
  ↓
F001_SPEC → F001_RENDER → F001_QC
  ↓
F002+ bulk tasks
  ↓
Z999_FINAL_AUDIT
```

Fast mode has one initial human gate, then relies on verifier authority, Santa NICE/NICE review, repair tasks, logs, metrics, and final audit. It is the recommended mode when you want a real loop rather than repeated manual pauses.

## Balanced and strict modes

```text
balanced: G000_START_REVIEW → boundary test → F001 pilot → H020_PILOT_REVIEW → bulk loop → final audit
strict:   G000_SETUP_REVIEW → H000_PLAN_REVIEW → boundary test → F001 pilot → H020_PILOT_REVIEW → bulk loop → final audit
```

## Task count

For `N` figures with `--tasks-per-figure 3`:

```text
fast     = 3N + 3
balanced = 3N + 4
strict   = 3N + 5
```

## Strong command sequence

```bash
python -m autopilot_nodekit start-from-prompt --workspace . --prompt-file PROJECT_PROMPT.md --gate-mode fast --force-codex-native
python -m autopilot_nodekit next-command --workspace .
python -m autopilot_nodekit approve-start --workspace . --summary "Spec, setup, permissions, task DAG, and fast-loop mode reviewed."
python -m autopilot_nodekit codex-prepare --workspace . --worker-id codex-interactive
bash runs/<run_id>/open_codex.sh
python -m autopilot_nodekit codex-finish --workspace . --run-id <run_id>
python -m autopilot_nodekit next-command --workspace .
```

## Non-human DONE rule

A non-human task cannot pass unless:

1. The worker result says `passed`.
2. The configured verifier succeeds, if present.
3. Santa reviewer A returns `NICE` with evidence.
4. Santa reviewer B returns `NICE` with evidence.

NodeKit is authoritative. If these checks fail, `passed` is normalized to `failed`.
