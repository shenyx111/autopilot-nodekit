# Prompt spec fast loop

NodeKit makes the user's prompt a project specification seed, not the loop controller.

## Minimal prompt

Create `PROJECT_PROMPT.md`:

```markdown
# Project
Nature paper figure production

# Goal
Generate 100 publication-ready figures for Nature.

# Inputs
data/

# Deliverables
For every figure: source-data record, plotting script, PDF, PNG, SVG, caption, journal check, QC evidence.

# Forbidden
Never fabricate data. Never use placeholders as completed outputs. Never modify raw data in place.

# Preference
Minimize human stops. Use fast gate mode unless a risk requires escalation.
```

## Strong command

```bash
python -m autopilot_nodekit start-from-prompt \
  --workspace . \
  --prompt-file PROJECT_PROMPT.md \
  --gate-mode fast \
  --force-codex-native
```

This creates:

```text
PROJECT_SPEC.yml
PROJECT_SPEC.md
PROJECT_SETUP.yml
SETUP_REVIEW.md
GOAL_CONTRACT.yml
GOAL_CONTRACT.md
TASK_REVIEW.md
REQUIREMENTS_LOCK.md
automation/manifest.yml
automation/manifest.live.md
AGENTS.md
.codex/*
.agents/skills/*
```

## Gate modes

```text
fast:
  G000_START_REVIEW -> H010_BOUNDARY_PERMISSION_TEST -> F001_SPEC/RENDER/QC -> F002+ bulk -> Z999_FINAL_AUDIT

balanced:
  G000_START_REVIEW -> H010_BOUNDARY_PERMISSION_TEST -> F001_SPEC/RENDER/QC -> H020_PILOT_REVIEW -> F002+ bulk -> Z999_FINAL_AUDIT

strict:
  G000_SETUP_REVIEW -> H000_PLAN_REVIEW -> H010_BOUNDARY_PERMISSION_TEST -> F001_SPEC/RENDER/QC -> H020_PILOT_REVIEW -> F002+ bulk -> Z999_FINAL_AUDIT
```

## Optional AI spec drafting

For complex project prompts, prepare a Codex spec-drafting handoff:

```bash
python -m autopilot_nodekit codex-draft-spec --workspace . --prompt-file PROJECT_PROMPT.md --gate-mode fast
bash runs/spec-draft-*/open_codex_spec.sh
python -m autopilot_nodekit project-spec-review --workspace .
python -m autopilot_nodekit start-from-spec --workspace . --spec PROJECT_SPEC.yml --force-codex-native
```

## Bulk loop

After startup approval:

```bash
python -m autopilot_nodekit approve-start --workspace . --summary "Project spec, setup, permissions, task DAG, and fast loop mode reviewed."
python -m autopilot_nodekit background-doctor --workspace .
python -m autopilot_nodekit launch-background --workspace . --worker-id codex-worker --max-cycles 0
```

The background worker and operator should handle routine task execution, repair, stale recovery, and repair resolution. Use `next-command` for diagnosis or supervision. For interactive Codex debugging, the manual sequence is:

```bash
python -m autopilot_nodekit codex-prepare --workspace . --worker-id codex-interactive
bash runs/<run_id>/open_codex.sh
python -m autopilot_nodekit codex-finish --workspace . --run-id <run_id>
```

For non-interactive batch use after pilot confidence is established:

```bash
python -m autopilot_nodekit worker-loop --workspace . --worker-id codex-worker --max-cycles 0
```
