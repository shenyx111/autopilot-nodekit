---
name: autopilot-smart-start
description: Use whenever the user mentions autopilot-nodekit or asks to run a prompt through this package. Converts the user prompt into startup files, asks missing settings, and starts only after required settings are resolved.
---

# Autopilot Smart Start

This is the mandatory first skill when the user says "基于 autopilot-nodekit" or otherwise asks to use this package.

## Fixed flow

1. Create or update `PROJECT_PROMPT.md` from the user's actual task prompt.
2. Run:

```bash
python -m autopilot_nodekit smart-start --workspace . --prompt-file PROJECT_PROMPT.md --force-codex-native
```

3. If `START_QUESTIONS.md` is produced, stop and ask the user only those missing settings. Do not start the task graph.
4. After the user answers, write `START_ANSWERS.yml` with `confirmed: true`, then rerun smart-start.
5. Once the graph exists, use the background worker and operator for routine progress:

```bash
python -m autopilot_nodekit background-doctor --workspace .
python -m autopilot_nodekit launch-background --workspace . --worker-id codex-worker --max-cycles 0
```

## Do not silently guess these fields

- `gate_mode`: fast / balanced / strict
- `task_scale`: smoke / standard / prod
- `artifact_count`
- `target_journal` or target venue for figure projects
- generated deliverables if file outputs are unclear

## Gate modes

- `fast`: startup approval, boundary test, automatic F001 pilot guard, bulk loop, final audit.
- `balanced`: startup approval, boundary test, human F001 pilot review, bulk loop, final audit.
- `strict`: separate setup review, plan review, boundary test, human F001 pilot review, bulk loop, final audit.

## Task scales

- `smoke`: 2 tasks/artifact.
- `standard`: 3 tasks/artifact.
- `prod`: 4 tasks/artifact including separate compliance check.

## Background policy

Do not assume tmux. Run:

```bash
python -m autopilot_nodekit background-doctor --workspace .
python -m autopilot_nodekit launch-background --workspace . --worker-id codex-worker --max-cycles 0
```

`--max-cycles 0` means NodeKit does not set a cycle limit. Do not add wall-clock timeout limits to background workers unless the user explicitly asks.
