# Bundle notes — v0.9.3

This v0.9.3 bundle focuses on GitHub-ready, long-running Codex execution with operator automation and mainline-first scheduling. The main problems addressed in real use were:

- demo/figure template contamination in non-figure projects;
- Windows `/bin/sh` and PowerShell redirect issues;
- empty `worker.command` defaults;
- invalid Codex `job_max_runtime_seconds = 0`;
- tmux false positives when tmux exists but cannot create sessions;
- background workers losing `PYTHONPATH`;
- stale `running` tasks with no worker result;
- repair tasks passing without releasing a failed parent;
- low-observability background logs.

Key new commands:

```bash
python -m autopilot_nodekit background-status --workspace . --worker-id codex-worker
python -m autopilot_nodekit recover-stale --workspace . --run-id <RUN_ID> --mark-failed
python -m autopilot_nodekit resolve-by-repair --workspace . --failed-task-id <FAILED> --repair-task-id <PASSED_REPAIR>
```

Key new generated files:

```text
.nodekit/nodekit
.nodekit/nodekit.ps1
.nodekit/codex_worker.sh
.nodekit/codex_worker.ps1
automation/background/<worker>.heartbeat.json
logs/background/<worker>.heartbeat.jsonl
```


## Shell-safety hardening

Adds verifier/bootstrap shell-safety lint. Verifier commands now block accidental command substitution and mutating commands such as `sbatch`, `scancel`, `srun`, `qsub`, and `rm -rf` unless explicitly allowed after human review. This prevents report-text checks from accidentally executing Slurm or destructive shell commands.


## v0.9.3

This bundle adds operator automation and mainline-first scheduling. It is designed so routine repair task creation, repair resolution, and stale-run recovery are handled by NodeKit instead of requiring user reminders. Historical failed repair branches are ignored once downstream mainline progress has moved on.
