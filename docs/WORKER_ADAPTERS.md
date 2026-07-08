# Worker adapters

A worker adapter is `automation/config.yml`. v0.7.0 is Codex-first; shell remains the local demo/test adapter.

Codex non-interactive example:

```yaml
worker:
  agent: codex-cli
  command: 'codex exec --sandbox workspace-write --skip-git-repo-check --output-last-message "$AUTOPILOT_RUN_DIR/codex_final.md" - < "$AUTOPILOT_PROMPT"'
  timeout_seconds: null
```

Interactive per-task example:

```yaml
worker:
  agent: codex-interactive
  command: ''
  timeout_seconds: null
```

Shell demo example:

```yaml
worker:
  agent: shell-demo
  command: 'python examples/demo_worker.py'
  timeout_seconds: null
```

Workers must write `$AUTOPILOT_RUN_DIR/worker_result.json`. Non-human tasks that declare `review_policy.required: true` must include Santa NICE/NICE review evidence.
