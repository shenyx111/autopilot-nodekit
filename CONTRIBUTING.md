# Contributing

Thanks for improving Autopilot NodeKit.

Before opening a PR, run these commands from the package root, the folder that contains `pyproject.toml`, `autopilot_nodekit/`, and `tests/`:

```bash
python -m pip install -e ".[dev]"
python -m compileall -q autopilot_nodekit tests
python -m pytest -q
```

Please keep PRs focused. This project is a control plane, so changes should preserve:

- tasks should only be marked done after their verifier passes;
- failed tasks should go through the repair flow instead of being silently retried;
- important outputs and evidence should remain traceable in `runs/` and `automation/events.jsonl`;
- Windows, Linux, and macOS behavior should be explicit when a change touches shell commands, paths, or background workers;
- private data, logs, credentials, local databases, and real run directories should not be committed.

For changes affecting background workers, include a short note about Linux/macOS/Windows behavior.
