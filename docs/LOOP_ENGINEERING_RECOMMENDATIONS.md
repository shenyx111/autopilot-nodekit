# Loop engineering recommendations applied in this bundle

This bundle uses a conservative Codex-first loop architecture.

## Design principles

1. A loop is not repeated prompting. It needs a goal, state, tools, verification, repair, metrics, and a stopping condition.
2. Durable state must live outside the conversation. NodeKit uses SQLite, `automation/manifest.live.md`, `runs/`, `memory/nodes/`, `LOOP_STATE.md`, and `PLANS.md`.
3. Human gates should be risk-based. NodeKit supports `fast`, `balanced`, and `strict` gate modes so bulk loops do not stop unnecessarily.
4. Large batches must not collapse into vague tasks. The figure generator creates 303-305 tasks for 100 figures depending on gate mode.
5. Verifiers override agent self-report. A worker cannot pass a task if the verifier fails.
6. Every non-human pass requires Santa NICE/NICE review with evidence.
7. Use repair tasks, not hidden retries. QC failures should insert focused graph-patch repair tasks with evidence and memory selectors.
8. Project prompts should become specs. NodeKit turns `PROJECT_PROMPT.md` into `PROJECT_SPEC.yml`, then into contract, manifest, and agent handoffs.

## Mapping to Codex-native mechanisms

- Goal: `codex-goal`, `codex-contract-goal`, and `codex-spec-goal` generate native `/goal` commands.
- Project instructions: `AGENTS.md` encodes hard gates, verifier authority, Santa review, and fast-loop policy.
- Skills: `.agents/skills` contains reusable workflows, including `$autopilot-project-spec`, `$autopilot-review-gated-figure-loop`, and `$autopilot-santa-review`.
- Subagents: `.codex/agents` includes read-only explorer/checker roles plus Santa reviewer A/B.
- Permission boundary: `.codex/config.toml` uses `workspace-write` and `on-request` by default; task plans start with a boundary test.
- Evidence: every run has prompt/context/memory/result/verifier/control artifacts.

## Sources reviewed

- O'Reilly Radar / Addy Osmani, "Loop Engineering" — automations, worktrees, skills, plugins/connectors, subagents, and external memory.
- OpenAI Codex goal docs — durable `/goal`, validation loop, checkpoint log, pause/resume/clear.
- OpenAI Codex best practices — goal/context/constraints/done-when, AGENTS.md, validation, sandbox/approval discipline.
- OpenAI Codex skills docs — skills as reusable workflows with `SKILL.md` and progressive disclosure.
- OpenAI Codex subagents docs — explicit parallel/explorer/checker agents, with token-cost tradeoffs.
- OpenAI Codex approvals/security and non-interactive docs — prefer explicit sandbox modes and reviewable commands.
