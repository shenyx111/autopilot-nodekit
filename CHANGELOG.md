# Changelog

## v0.9.3

- Made operator/supervisor automation the default path in `worker-loop` for routine repair/recover/resolve transitions.
- Added mainline-first scheduling so historical failed repair branches do not preempt current ready work or completed downstream progress.
- Added `operator-step` and `operator-loop` for explicit supervisor actions.
- `launch-background` passes operator settings into worker-loop.
- `--no-auto-operator` disables the built-in operator for advanced users.
- Fixed `--lease-seconds 0` so it truly means no lease expiry.
- Added regression tests for operator stale recovery, live heartbeat monitoring, repair depth limits, mainline-first scheduling, generated Codex-native guidance, and shell-safety CLI behavior.
- README and public docs now use one bilingual entry point, with Chinese first and English second.
