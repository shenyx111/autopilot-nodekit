# Integration with Codex skills

v0.7 installs repo-local Codex skills under `.agents/skills`.

## Recommended skills

```text
$autopilot-project-spec
$autopilot-review-gated-figure-loop
$autopilot-santa-review
$autopilot-nodekit-worker-result
$autopilot-nodekit-memory-curator
$autopilot-nodekit-graph-curator
```

## Rule of thumb

Skills are procedures. They are not the source of truth.

Source of truth stays in:

```text
PROJECT_SPEC.yml
GOAL_CONTRACT.yml
PROJECT_SETUP.yml
automation/manifest.yml
automation/autopilot.sqlite
runs/
memory/nodes/
automation/events.jsonl
```

## Preferred startup

```bash
python -m autopilot_nodekit start-from-prompt --workspace . --prompt-file PROJECT_PROMPT.md --gate-mode fast --force-codex-native
python -m autopilot_nodekit next-command --workspace .
```
