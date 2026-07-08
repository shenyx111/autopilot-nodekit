# Changelog

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
