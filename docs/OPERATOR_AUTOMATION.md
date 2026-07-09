# Operator automation

Autopilot NodeKit separates three roles:

1. **Background worker**: claims and executes ready tasks.
2. **Operator/supervisor**: handles routine control-plane transitions.
3. **Human**: approves gates and risky actions.

The user should not need to manually run `next-command` after every routine repair. In v0.9.3, `worker-loop` runs the operator by default whenever no ready task is available.

## What the operator may do automatically

- Add a focused repair task for an active failed task.
- Resolve a failed parent by a passed repair task.
- Recover a stale running task into a failed evidence-bearing run, so repair can proceed.
- Monitor background runs and avoid premature `codex-finish`.

## What the operator must not do

- Approve human gates.
- Submit or cancel Slurm/DFT/COMSOL/cloud jobs.
- Delete or overwrite user data.
- Use credentials or external paid services.
- Override verifier/Santa failures by assertion.

## Mainline-first scheduling

A failed task is actionable only when it is still on the active frontier:

- it blocks planned/blocked/review-pending downstream work; or
- it is the current leaf failure and no later mainline task has moved on.

Historical failed repair branches are ignored once downstream mainline progress has been released. This prevents the loop from going `F001 → F002 → old F001 repair` because an old repair side-branch still has failed status.

## Manual diagnosis

You can still inspect the control plane:

```bash
python -m autopilot_nodekit next-command --workspace .
python -m autopilot_nodekit status --workspace .
python -m autopilot_nodekit background-status --workspace . --worker-id codex-worker
```

But in a healthy background run, these are diagnostic commands, not buttons the user must press repeatedly.
