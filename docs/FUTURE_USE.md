# Future use path

## Stage 1: Prompt-spec local loop

1. Write `PROJECT_PROMPT.md`.
2. Run `start-from-prompt --gate-mode fast`.
3. Approve the one startup gate.
4. Use `next-command` and `codex-prepare` / `codex-finish` until the first artifact is stable.
5. Switch to `worker-loop` only after verifier/Santa evidence looks reliable.

## Stage 2: AI-generated project specs

Use Codex to draft or refine `PROJECT_SPEC.yml`:

```bash
python -m autopilot_nodekit codex-draft-spec --workspace . --prompt-file PROJECT_PROMPT.md --gate-mode fast
bash runs/spec-draft-*/open_codex_spec.sh
python -m autopilot_nodekit start-from-spec --workspace . --spec PROJECT_SPEC.yml --force-codex-native
```

## Stage 3: Better repair graph mutation

Train Codex prompts to use graph patches:

- insert focused repair tasks after QC failure
- block a task when source data is missing
- supersede a task when the project spec changes
- never delete task history

## Stage 4: Multi-worker execution

Only parallelize independent tasks.

Recommended pattern:

```text
worker w1 -> git worktree .worktrees/w1
worker w2 -> git worktree .worktrees/w2
worker w3 -> git worktree .worktrees/w3
merge/review gate -> main worktree
```

Add a merge coordinator task that reads run diffs and resolves conflicts.

## Stage 5: Sandboxed tools

Use Docker/E2B when Codex runs generated scripts, installs packages, or operates on untrusted data.

## Stage 6: Project-specific skills

Add or edit the included Codex skills:

```text
.agents/skills/autopilot-project-spec/SKILL.md
.agents/skills/autopilot-review-gated-figure-loop/SKILL.md
.agents/skills/autopilot-santa-review/SKILL.md
.agents/skills/autopilot-nodekit-worker-result/SKILL.md
```

Skills define procedures and policies. SQLite + manifest + raw evidence remain the source of truth.
