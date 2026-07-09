# Changelog

## v0.9.1

- Added verifier/bootstrap shell-safety lint to block accidental command substitution and mutating Slurm/destructive commands inside deterministic verifiers.
- Added `shell-safety-lint` CLI for prechecking commands.
- Verifier logs now include shell-safety findings.


## v0.9.0

- Added non-figure workflow planning for `science_workflow`, `matlantis_workflow`, `materials_dft_sevennet`, and `rag_local_llm`; smart-start no longer forces every project through the journal-figure template.
- Added `.nodekit` runtime wrappers for stable Python/PYTHONPATH and Codex worker invocation.
- Hardened `background-doctor`: real tmux smoke test, Python import check, Codex CLI check, worker.command check, invalid Codex timeout detection, platform hook check.
- Added `detached` backend and made it the Windows-first default; fixed PowerShell stdout/stderr split.
- `launch-background` now records backend/PID/Python/package metadata and avoids crashing on duplicate tmux sessions.
- Worker loop now writes heartbeat JSON/JSONL for observability.
- Added `background-status`, `recover-stale`, and `resolve-by-repair`.
- `next-command` no longer tells users to prematurely `codex-finish` background runs without a worker result.
- Removed invalid Codex `job_max_runtime_seconds = 0`; NodeKit no-timeout is expressed through worker-loop controls.

## v0.8.0

- Added `smart-start`, the fixed trigger flow for natural-language prompts and `autopilot-nodekit` keyword usage.
- Added mandatory startup questions for missing `gate_mode`, `task_scale`, artifact count, target venue/journal, and unclear deliverables.
- Added task scale tiers: `smoke`, `standard`, `prod`.
- Added `background-doctor` and `launch-background` with tmux/nohup/setsid/powershell/foreground detection.
- Changed default worker/verifier timeout policy to no wall-clock timeout; `--max-cycles 0` means unlimited cycles.
- Added `autopilot-smart-start` Codex skill and updated AGENTS.md trigger rules.
- Added docs for layer command invocation.

## v0.7.0

- Prompt-to-project-spec startup.
- Fast/balanced/strict gate modes.
- Santa dual review enforcement.


## v0.9.1 shell-safety hardening

Adds verifier/bootstrap shell-safety lint. Verifier commands now block accidental command substitution and mutating commands such as `sbatch`, `scancel`, `srun`, `qsub`, and `rm -rf` unless explicitly allowed after human review. This prevents report-text checks from accidentally executing Slurm or destructive shell commands.
