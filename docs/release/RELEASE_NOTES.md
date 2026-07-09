# Release notes — v0.9.3 open-source bundle

v0.9.3 makes Autopilot NodeKit feel like a real background loop, with routine repair, recovery, and repair resolution handled by the worker/operator path.

## Highlights

- `worker-loop` now includes the operator/supervisor automation by default.
- The operator can create focused repair tasks, resolve failed parents with passed repair evidence, and recover stale runs without asking the user for routine control-plane work.
- Scheduling is now mainline-first: historical failed repair branches should not drag the project back after downstream work has already released.
- `next-command` is still available for diagnosis, but normal background runs should not require the user to execute every routine command.

## Still human-gated

NodeKit still stops for startup/pilot/final gates, unclear permissions, destructive operations, credentials, external paid services, expensive compute submission/cancellation, and repeated repair failures.

## Upgrade note

Use this release for new projects. If you replace an active workspace, pause workers first and keep the existing run evidence until the new control plane has been checked.
