# GitHub publishing guide

## Recommended repository settings

1. Create a new GitHub repository.
2. Keep it private until you review the release contents.
3. Push this directory as the initial commit.
4. Confirm CI passes.
5. Review `README.md`, `SECURITY.md`, `LICENSE`, and `docs/release/`.
6. Switch repository visibility to public when ready.

## Local publish commands

```bash
git init
git add .
git commit -m "Release Autopilot NodeKit v0.9.3"
git branch -M main
git remote add origin https://github.com/<OWNER>/autopilot-nodekit.git
git push -u origin main
```

## Do not publish

- Real user workspaces.
- `runs/`, `logs/`, `memory/nodes/`, real `automation/autopilot.sqlite`, or `automation/events.jsonl`.
- Raw research data, private documents, model weights, credentials, API keys, or cluster-specific secrets.
- Proprietary third-party software or generated outputs that you are not allowed to share.
