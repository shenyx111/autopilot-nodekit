# v0.9 Bootstrap hardening guide

This release focuses on the uncomfortable points seen in real Windows/Linux runs: demo-template drift, empty worker commands, invalid Codex timeout config, missing PYTHONPATH in tmux/detached workers, stale `running` tasks, weak background logs, and repair tasks that pass without releasing the failed parent.

## Reliable startup sequence

```bash
python -m autopilot_nodekit smart-start --workspace . --prompt-file PROJECT_PROMPT.md --force-codex-native
python -m autopilot_nodekit background-doctor --workspace .
python -m autopilot_nodekit validate --workspace . --strict
python -m autopilot_nodekit approve-start --workspace . --summary 'Project spec, Layer 0 setup, contract, task manifest, permissions, and loop mode reviewed.'
python -m autopilot_nodekit launch-background --workspace . --worker-id codex-worker --max-cycles 0
```

If the project is not a figure batch, prefer an explicit `PROJECT_SPEC.yml` with a non-figure `project.type`, then run:

```bash
python -m autopilot_nodekit start-from-spec --workspace . --spec PROJECT_SPEC.yml --force-codex-native
```

Supported non-figure project types include:

```text
science_workflow
matlantis_workflow
materials_dft_sevennet
rag_local_llm
```

## New or hardened commands

```bash
python -m autopilot_nodekit background-doctor --workspace . --json
python -m autopilot_nodekit background-status --workspace . --worker-id codex-worker
python -m autopilot_nodekit recover-stale --workspace . --age-minutes 30
python -m autopilot_nodekit recover-stale --workspace . --run-id <RUN_ID> --mark-failed
python -m autopilot_nodekit resolve-by-repair --workspace . --failed-task-id <FAILED> --repair-task-id <PASSED_REPAIR>
```

## Runtime wrappers

`install-codex-native`, `smart-start`, and config creation now install `.nodekit/` wrappers:

```text
.nodekit/nodekit
.nodekit/nodekit.ps1
.nodekit/codex_worker.sh
.nodekit/codex_worker.ps1
.nodekit/env.json
```

Use these wrappers to avoid ad hoc `PYTHONPATH` and nested `AUTOPILOT_*` environment leakage.

## Background worker heartbeat

The worker loop now writes heartbeat files:

```text
automation/background/<worker-id>.heartbeat.json
automation/background/<worker-id>.heartbeat.jsonl
logs/background/<worker-id>.heartbeat.jsonl
```

These are the first files to inspect when a background process seems stuck.

## Windows notes

Windows should normally use the `detached` backend. The PowerShell backend is available, but stdout and stderr are written to separate files to avoid `Start-Process` redirection errors. Codex Stop hooks use direct Python invocation, not `/bin/sh`.

## Linux notes

Linux uses tmux when a real tmux smoke test passes. `background-doctor` now tests `tmux -V`, `tmux new-session`, `has-session`, and cleanup instead of trusting `command -v tmux`.

## Stale task policy

Do not manually edit SQLite. If a task remains `running` but the worker is gone, use:

```bash
python -m autopilot_nodekit recover-stale --workspace . --run-id <RUN_ID> --mark-failed
```

This converts the abandoned run into a failed evidence-bearing run so the normal repair loop can continue.

## Repair-release policy

If a repair task passes but the failed parent still blocks downstream work, use:

```bash
python -m autopilot_nodekit resolve-by-repair --workspace . --failed-task-id <FAILED> --repair-task-id <PASSED_REPAIR>
```

This marks the failed parent as superseded and rewires downstream gating edges to the repair evidence.

## Shell-safety lint

NodeKit includes verifier/bootstrap shell-safety linting. Deterministic verifier
commands are expected to be read-only. The runner blocks common accidental
side-effect patterns before execution, including:

- backtick command substitution, for example ``rg "`sbatch`" report.md``;
- `$()` command substitution;
- direct `sbatch`, `scancel`, `srun`, `qsub`, or `qdel` inside a verifier;
- `rm -rf` style destructive deletion.

Use the linter directly:

```bash
python -m autopilot_nodekit shell-safety-lint --purpose verifier --command 'rg "`sbatch`" report.md'
```

For Slurm workflows, put job submission/cancellation in explicit tasks with
human/resource gates. Verifiers should use read-only probes such as `squeue`,
`sacct`, parser checks, JSON/YAML assertions, or Python scripts.
