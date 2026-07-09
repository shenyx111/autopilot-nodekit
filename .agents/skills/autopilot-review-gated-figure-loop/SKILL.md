---
name: autopilot-review-gated-figure-loop
description: Use for large artifact batches such as 100 journal figures where Codex/NodeKit must generate many tasks, run a boundary test, pilot the first artifact, minimize human stops when requested, then loop with Santa review, repair, and final verification.
---

# Autopilot Figure Loop

Use this skill whenever the user asks for many journal figures, plots, panels, charts, or repeated deliverables.

## Preferred startup

Start from a project prompt and let NodeKit draft the spec:

```bash
python -m autopilot_nodekit start-from-prompt --workspace . --prompt-file PROJECT_PROMPT.md --gate-mode fast --force-codex-native
```

If the user wants more review, use `--gate-mode balanced` or `--gate-mode strict`.

## Task scale

For `N` figures/artifacts, do not create a tiny vague task list. With `--tasks-per-figure 3`:

- fast: `3N + 3`
- balanced: `3N + 4`
- strict: `3N + 5`

For 100 figures, fast mode should still produce 303 tasks.

## Human stops

Fast mode has one manual startup approval. After that, do not keep stopping for human review. Use:

- boundary permission test
- verifier authority
- F001_QC automatic pilot guard
- Santa dual-review after each non-human task
- repair tasks on failure
- final audit

Balanced mode adds one human pilot gate. Strict mode keeps setup, plan, and pilot gates.

## Background-first loop

```bash
python -m autopilot_nodekit background-doctor --workspace .
python -m autopilot_nodekit launch-background --workspace . --worker-id codex-worker --max-cycles 0
```

Use `codex-prepare` and `codex-finish` only for manual debugging, pilot inspection, or a human-visible task dialog. Routine repair, stale recovery, and passed-repair resolution should be handled by the worker-loop operator.

## Self-correction rule

Before a non-human task is marked passed, run Santa dual-review and require NICE/NICE. If a figure fails QC, do not mark it passed. Insert focused repair tasks with `graph_patch`, using `after_attempt` or `depends_on` correctly, and include memory selectors so future tasks inherit failure evidence.


## Task scale and startup rules

Use `smart-start` first for all natural-language prompts. Do not silently default gate mode or task scale in the fixed flow.

Task scale controls per-figure graph density:

- `smoke`: 2 tasks per figure, about `2N + gates` total tasks.
- `standard`: 3 tasks per figure, about `3N + gates` total tasks.
- `prod`: 4 tasks per figure, about `4N + gates` total tasks with separate journal/compliance check.

For 100 figures in fast mode:

- smoke ≈ 203 tasks
- standard ≈ 303 tasks
- prod ≈ 403 tasks

Use background detection before launching long loops:

```bash
python -m autopilot_nodekit background-doctor --workspace .
python -m autopilot_nodekit launch-background --workspace . --worker-id codex-worker --max-cycles 0
```
