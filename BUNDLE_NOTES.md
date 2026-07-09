# Bundle notes — v0.9.1

This v0.9.1 bundle focuses on GitHub-ready, long-running Codex execution. It includes smart-start, background-aware execution, bootstrap/background hardening, and shell-safety checks. The main problems addressed in real use were:

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


## v0.9.1 shell-safety hardening

Adds verifier/bootstrap shell-safety lint. Verifier commands now block accidental command substitution and mutating commands such as `sbatch`, `scancel`, `srun`, `qsub`, and `rm -rf` unless explicitly allowed after human review. This prevents report-text checks from accidentally executing Slurm or destructive shell commands.
