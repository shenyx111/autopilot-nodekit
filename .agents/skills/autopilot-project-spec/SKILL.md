---
name: autopilot-project-spec
description: Use when a fuzzy user prompt should become a complete Autopilot NodeKit PROJECT_SPEC.yml before task generation; v0.8 requires asking missing startup settings instead of silently guessing.
---

# Autopilot Project Spec

Use this skill after `$autopilot-smart-start` determines the project is ready to convert into a spec.

## Required behavior

Do not make the user write a long orchestration prompt. Convert the project prompt into `PROJECT_SPEC.yml`, then let NodeKit generate:

- `PROJECT_SETUP.yml`
- `GOAL_CONTRACT.yml`
- `automation/manifest.yml`
- `TASK_REVIEW.md`
- `REQUIREMENTS_LOCK.md`

But do not start execution if these are missing or ambiguous:

- `gate_mode`: fast / balanced / strict
- `task_scale`: smoke / standard / prod
- artifact count
- target journal / venue
- deliverable file types if unclear

Use `smart-start` as the primary command:

```bash
python -m autopilot_nodekit smart-start --workspace . --prompt-file PROJECT_PROMPT.md --force-codex-native
```

If questions are required, NodeKit writes:

- `START_QUESTIONS.md`
- `START_ANSWERS.yml.template`

After answers:

```bash
python -m autopilot_nodekit smart-start --workspace . --prompt-file PROJECT_PROMPT.md --answers START_ANSWERS.yml --force-codex-native
```

## Spec must include

- project name, type, artifact count, journal/target venue
- gate mode and task scale
- inputs and missing-input policy
- outputs and per-artifact deliverables
- Definition of Done
- forbidden actions
- permissions and sandbox boundary
- verification commands
- repair policy
- Codex-native files, skills, subagents
- background backend/timeout policy

No clear spec means no automated loop.
