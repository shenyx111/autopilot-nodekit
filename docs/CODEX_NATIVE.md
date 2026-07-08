# Codex-native integration in v0.7.0

NodeKit uses Codex as the worker and keeps a durable outer loop outside the model context.

## Files installed by `install-codex-native`

```text
AGENTS.md
LOOP_STATE.md
PLANS.md
.codex/config.toml
.codex/hooks.json
.codex/hooks/autopilot_stop_render.py
.codex/agents/autopilot-explorer.toml
.codex/agents/autopilot-checker.toml
.codex/agents/autopilot-santa-reviewer-a.toml
.codex/agents/autopilot-santa-reviewer-b.toml
.agents/skills/*/SKILL.md
```

## Prompt-to-spec entrypoint

```bash
python -m autopilot_nodekit start-from-prompt --workspace . --prompt-file PROJECT_PROMPT.md --gate-mode fast --force-codex-native
```

## AI-assisted spec drafting

```bash
python -m autopilot_nodekit codex-draft-spec --workspace . --prompt-file PROJECT_PROMPT.md --gate-mode fast
bash runs/spec-draft-*/open_codex_spec.sh
python -m autopilot_nodekit start-from-spec --workspace . --spec PROJECT_SPEC.yml --force-codex-native
```

## Native goals

Project goal:

```bash
python -m autopilot_nodekit codex-contract-goal --workspace . --output CODEX_PROJECT_GOAL.md
```

Task goal:

```bash
python -m autopilot_nodekit codex-goal --workspace . --task-id F001_RENDER --output CODEX_GOAL.md
```

## Interactive per-task Codex handoff

```bash
python -m autopilot_nodekit codex-prepare --workspace . --worker-id codex-interactive
bash runs/<run_id>/open_codex.sh
python -m autopilot_nodekit codex-finish --workspace . --run-id <run_id>
```

The prepared prompt includes task contract, memory selection, verifier rule, and Santa dual-review requirement.
