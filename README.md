# Autopilot NodeKit v0.8.0 — Smart-start + Background-aware Codex bundle
## 中文简明示例

面向大众的中文使用示例见：[`README.zh-CN.md`](README.zh-CN.md)。


This bundle is a Codex-native loop control plane for durable task graphs, verifier-authoritative DONE, Santa dual review, repair loops, non-lossy memory, and auditable runs.

v0.8 changes the startup model: the user should not have to remember a long control prompt. If they mention `autopilot-nodekit`, the agent should create `PROJECT_PROMPT.md` and run the fixed smart-start flow.

## The reliable startup command

```bash
python -m autopilot_nodekit smart-start --workspace . --prompt-file PROJECT_PROMPT.md --force-codex-native
```

If required settings are missing, it writes:

```text
START_QUESTIONS.md
START_ANSWERS.yml.template
```

Fill the answers, set `confirmed: true`, then rerun:

```bash
python -m autopilot_nodekit smart-start --workspace . --prompt-file PROJECT_PROMPT.md --answers START_ANSWERS.yml --force-codex-native
```

## Required settings smart-start will not silently guess

- `gate_mode`: `fast`, `balanced`, or `strict`
- `task_scale`: `smoke`, `standard`, or `prod`
- `artifact_count`
- `target_journal` / target venue
- generated deliverables if unclear

## Gate modes

- `fast`: one startup approval, boundary test, automatic F001 pilot guard, bulk loop, final audit.
- `balanced`: one startup approval, boundary test, human F001 pilot review, bulk loop, final audit.
- `strict`: setup review, plan review, boundary test, human F001 pilot review, bulk loop, final audit.

Verifier, Santa dual review, repair, evidence, memory, logs, and final audit remain mandatory in all modes.

## Task scales

- `smoke`: 2 tasks/artifact.
- `standard`: 3 tasks/artifact.
- `prod`: 4 tasks/artifact including separate journal/compliance check.

For 100 figures in fast mode this is about 203 / 303 / 403 tasks.

## Background execution

Do not assume tmux. Detect available options first:

```bash
python -m autopilot_nodekit background-doctor --workspace .
```

Launch the best available background backend:

```bash
python -m autopilot_nodekit launch-background --workspace . --worker-id codex-worker --max-cycles 0
```

`--max-cycles 0` means unlimited cycles. NodeKit defaults do not impose wall-clock timeouts on worker or verifier commands.

## Main loop

After startup, keep using:

```bash
python -m autopilot_nodekit next-command --workspace .
```

For interactive per-task Codex dialogs, the usual sequence is:

```bash
python -m autopilot_nodekit codex-prepare --workspace . --worker-id codex-interactive
bash runs/<run_id>/open_codex.sh
python -m autopilot_nodekit codex-finish --workspace . --run-id <run_id>
```

## Layer command map

See `docs/SMART_START_BACKGROUND.md` for the complete layer-to-command map.

## Verification

```bash
python -m compileall -q autopilot_nodekit tests
python -m pytest -q
python -m autopilot_nodekit validate --workspace . --strict
```
