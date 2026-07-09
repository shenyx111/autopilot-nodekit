# Contributing

Thanks for improving Autopilot NodeKit.

Before opening a PR:

```bash
python -m pip install -e '.[dev]'
python -m compileall -q autopilot_nodekit tests
python -m pytest -q
```

Please keep PRs focused. This project is a control plane, so changes should preserve:

- verifier-authoritative DONE;
- repair loops instead of silent retries;
- durable evidence in `runs/` and events;
- explicit Windows/Linux behavior;
- no accidental commits of private data, logs, credentials, or real run directories.

For changes affecting background workers, include a short note about Linux/macOS/Windows behavior.
