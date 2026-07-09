# Release notes — v0.9.1 open-source bundle

This is a GitHub-ready release of Autopilot NodeKit v0.9.1.

Focus areas:

- safer startup for Windows and Linux;
- `.nodekit` wrappers for stable Python/Codex execution;
- non-figure workflow project types;
- background heartbeat and status inspection;
- stale-run recovery;
- repair-based graph release;
- shell-safety lint for verifier commands;
- concise public documentation.

This release intentionally excludes real run artifacts, private data, model weights, Slurm outputs, and user-specific workspaces.

CI note: tests are split into smaller groups to avoid plugin/environment interaction issues in long pytest sessions.
