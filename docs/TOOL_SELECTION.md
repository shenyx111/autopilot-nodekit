# Tool selection

NodeKit is intentionally conservative. It uses a mainstream local base and treats agent frameworks as pluggable.

## Core tools

### Python

Portable, easy to inspect, easy to modify.

### SQLite

Durable local database with transactions, WAL, and FTS. Good enough for thousands of local tasks.

### tmux

Simple background worker supervision that works well over SSH and local terminals.

### git

Recommended for all coding runs. For parallel workers, use a separate worktree per worker/task.

## Worker tools

### Codex CLI / OpenAI Agents SDK

Good when your main model/workflow is OpenAI-based. Agents SDK can later manage agent loops, sessions, tracing, guardrails, and handoffs.

### Claude Code

Good for repository-local coding and skill/hook workflows. Skills are useful for procedures; hooks are useful for deterministic gates.

### Aider

Good terminal pair-programming worker with git-oriented workflow.

### OpenHands

Good when you want an always-on software engineering agent/control-center style setup.

### mini-SWE-agent

Good when you want a minimal, hackable issue-solving worker.

## Optional orchestration upgrades

### LangGraph

Use when you want a formal graph runtime with checkpointers and stores.

### Temporal

Use when local tmux/SQLite is no longer enough and you need production durable execution.

### Prefect

Use when you want a simpler workflow UI/scheduler/retry system.

## MCP policy

MCP is a tool connection layer, not the task graph source of truth. Add MCP servers only when they directly help a task. Prefer:

- filesystem server scoped to workspace
- git server scoped to repo
- GitHub MCP with least privilege
- Context7 for current docs
- memory MCP only as an auxiliary interface, not the authoritative store

Use read-only modes and sandboxing when possible.
