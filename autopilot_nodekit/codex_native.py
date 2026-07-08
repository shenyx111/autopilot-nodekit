from __future__ import annotations

from pathlib import Path
from typing import Dict

from .util import write_text


AGENTS_MD = '# AGENTS.md\n\n## Project identity\n\nThis repository is a Codex-native local autopilot control plane.\n\nUse Autopilot NodeKit as the outer loop. Do not create independent unbounded inner loops unless the task explicitly asks for them.\n\n## Core commands\n\n- Install: `python -m pip install -e .`\n- Demo: `make demo`\n- Compile check: `python -m compileall -q autopilot_nodekit`\n- Tests: `python -m pytest -q`\n- Status: `python -m autopilot_nodekit status --workspace .`\n- Validate graph: `python -m autopilot_nodekit validate --workspace .`\n- Codex-native files: `python -m autopilot_nodekit install-codex-native --workspace .`\n- Generate a native goal: `python -m autopilot_nodekit codex-goal --workspace . --task-id T001`\n- Preferred prompt-to-loop startup: `python -m autopilot_nodekit start-from-prompt --workspace . --prompt-file PROJECT_PROMPT.md --gate-mode fast --force-codex-native`\n- AI draft/refine project spec: `python -m autopilot_nodekit codex-draft-spec --workspace . --prompt-file PROJECT_PROMPT.md --gate-mode fast`\n- Start from an explicit spec: `python -m autopilot_nodekit start-from-spec --workspace . --spec PROJECT_SPEC.yml --force-codex-native`\n- Legacy strict figure startup: `python -m autopilot_nodekit start-figures --workspace . --figures 100 --journal "target journal" --gate-mode strict`\n- Review Layer 0 setup: read `PROJECT_SETUP.yml` and `SETUP_REVIEW.md`.\n- Approve setup after human review: `python -m autopilot_nodekit approve-setup --workspace .`\n- Review plan: read `GOAL_CONTRACT.md`, `TASK_REVIEW.md`, `REQUIREMENTS_LOCK.md`, and `automation/manifest.live.md`.\n- Approve plan after human review: `python -m autopilot_nodekit approve-plan --workspace .`\n- Prepare one interactive Codex task dialog: `python -m autopilot_nodekit codex-prepare --workspace . --worker-id codex-interactive`\n- Finish an interactive Codex task after `worker_result.json` exists: `python -m autopilot_nodekit codex-finish --workspace . --run-id <run_id>`\n- Run non-interactive loop: `python -m autopilot_nodekit worker-loop --workspace . --worker-id codex-local`\n\n## Non-negotiable loop workflow\n\nPrefer PROJECT_SPEC-driven startup. A fuzzy user prompt should be converted into `PROJECT_SPEC.yml`, then into `PROJECT_SETUP.yml`, `GOAL_CONTRACT.yml`, and `automation/manifest.yml`.\n\nGate modes control how often humans stop the loop:\n\n- `fast`: one startup review, then boundary test, F001 automatic pilot guard, bulk loop, final audit.\n- `balanced`: one startup review, boundary test, F001 human pilot review, bulk loop, final audit.\n- `strict`: separate setup review, plan review, boundary test, F001 human pilot review, bulk loop, final audit.\n\nDo not collapse a large artifact request into a tiny task list. For `N` figures/artifacts, the graph must contain at least `N` tasks and normally at least `2N`; with 100 figures and 3 tasks per figure, fast mode creates 303 tasks, balanced 304, and strict 305.\n\n## Hard gate rules\n\n- In fast/balanced mode, `G000_START_REVIEW` starts as `review_pending` and is not claimable by workers; approve it with `approve-start` only after reading `PROJECT_SPEC.md`, `SETUP_REVIEW.md`, `GOAL_CONTRACT.md`, `TASK_REVIEW.md`, and `REQUIREMENTS_LOCK.md`.\n- In strict mode, `G000_SETUP_REVIEW` and `H000_PLAN_REVIEW` are separate `review_pending` gates.\n- `H010_BOUNDARY_PERMISSION_TEST` must depend on the approved startup/plan gate and must pass before figure work.\n- In fast mode, `F002+` bulk figure tasks must depend on `F001_QC`; this is the automatic pilot guard with no extra human stop.\n- In balanced/strict mode, `H020_PILOT_REVIEW` starts as `review_pending`, depends on `F001_QC`, and gates `F002+`.\n- `Z999_FINAL_AUDIT` must depend on all figure QC tasks.\n- Approvals must use `approve-start`, `approve-setup`, `approve-plan`, `approve-pilot`, or `approve-task`; do not edit SQLite manually.\n- Run `python -m autopilot_nodekit validate --workspace . --strict` after graph generation, approvals, graph patches, and before bulk work.\n\n## Safety rules\n\n- Do not mark a task passed unless the configured verifier passes.\n- Treat verifier output as more authoritative than the worker\'s self-reported status.\n- Every non-human task pass requires Santa dual-review: two independent reviewers must return NICE/NICE in `worker_result.json`.\n- If either reviewer returns NAUGHTY, repair the smallest issue, re-run the verifier, and re-run fresh reviews.\n- Do not edit `automation/autopilot.sqlite` directly.\n- Do not delete task history; supersede instead.\n- Treat `runs/` and `memory/nodes/` as durable evidence.\n- If `worker_result.json` is malformed, mark the run failed and preserve the malformed file.\n- If the next action would bypass a human gate, stop and report the gate that needs approval.\n\n## Graph rules\n\n- Use `depends_on` only for dependencies that must be `passed`.\n- Use `after_attempt` for diagnostic bridge tasks that should run after a failed, blocked, skipped, superseded, or passed predecessor.\n- Use `blocked_by` only for explicit blockers that should release after passed/skipped/superseded.\n- Use `parent_id` and `memory.required_task_ids` to inherit context from a failed parent.\n- Run `python -m autopilot_nodekit validate --workspace .` after graph patches.\n\n## Codex loop rules\n\nFor debugging, refactoring, benchmarking, reproduction, CI-fix, experiment, or artifact-batch tasks that may require multiple attempts, use `$autopilot-nodekit-loop-contract`. For prompt-to-spec startup, use `$autopilot-project-spec`. For journal figures or similar artifact batches, use `$autopilot-review-gated-figure-loop`. For per-task adversarial review, use `$autopilot-santa-review`.\n\nUse `python -m autopilot_nodekit codex-goal --workspace . --task-id <ID>` to render a pasteable Codex `/goal` command for a NodeKit task. Codex owns durable `/goal` state inside the active Codex thread; NodeKit owns the external task graph, verifier, review gates, and evidence trail.\n\nFor an interactive per-task Codex dialog:\n\n1. `python -m autopilot_nodekit codex-prepare --workspace . --worker-id codex-interactive`\n2. Run the printed `bash runs/<run_id>/open_codex.sh` command.\n3. Let Codex complete that one task and write `runs/<run_id>/worker_result.json`.\n4. `python -m autopilot_nodekit codex-finish --workspace . --run-id <run_id>`.\n\nKeep progress in `LOOP_STATE.md` or `PLANS.md`. Do not declare success without verifier evidence. If `/goal` is hidden, enable `features.goals = true` in `.codex/config.toml` or run `codex features enable goals`.\n'

LOOP_STATE_MD = """# Loop State

## Goal

Not started.

## Verifier

Not defined.

## Iterations

None yet.

## Current Status

Not started.

## Blockers

None known.
"""

PLANS_MD = """# PLANS.md

Use this file for long Codex tasks that need an external state trail.

Each active plan should include:

- outcome
- scope / non-goals
- verifier command
- iteration log
- open risks
- stop condition
"""

CODEX_CONFIG_TOML = """# Project-scoped Codex defaults for Autopilot NodeKit.
# Codex loads project .codex/ config only after the project is trusted.

sandbox_mode = "workspace-write"
approval_policy = "on-request"

[features]
# Enables native Codex Goal mode. You can also run: codex features enable goals
goals = true
hooks = true
multi_agent = true

[agents]
max_threads = 4
max_depth = 1
# job_max_runtime_seconds intentionally omitted: NodeKit background workers should not have a wall-clock timeout by default.
"""

CHECKER_AGENT_TOML = '''name = "autopilot_checker"
description = "Read-only checker for Autopilot NodeKit changes. Use after a maker patch to challenge correctness, graph semantics, verifier evidence, and scope control."
sandbox_mode = "read-only"
developer_instructions = """
You are the checker for an Autopilot NodeKit task. Do not edit files.

Review the patch, task graph semantics, verifier evidence, and memory nodes.
Flag only actionable issues: verifier bypass, depends_on misuse, malformed worker_result.json, hidden state loss, unbounded loops, unsafe scope expansion, or missing tests.
Return concise findings with file paths and exact verification commands.
"""
'''

EXPLORER_AGENT_TOML = '''name = "autopilot_explorer"
description = "Read-heavy explorer for mapping setup, tests, graph state, memory artifacts, and failure evidence before an Autopilot NodeKit patch."
sandbox_mode = "read-only"
developer_instructions = """
You are the explorer for an Autopilot NodeKit task. Do not edit files.

Read repository structure, automation/manifest.yml, automation/config.yml, AGENTS.md, LOOP_STATE.md, PLANS.md, relevant runs/, and memory/nodes/.
Return a compact evidence map: commands discovered, blockers, task graph risks, relevant memory nodes, and recommended verifier.
"""
'''


SANTA_REVIEWER_A_TOML = '''name = "autopilot-santa-reviewer-a"
description = "Santa Method reviewer A. Independent read-only reviewer that must return NICE or NAUGHTY for a single NodeKit task result."
sandbox_mode = "read-only"
developer_instructions = """
You are Santa reviewer A for an Autopilot NodeKit task. Do not edit files.

Review only the task contract, expected outputs, diff/artifacts, verifier log, memory/evidence files, and worker_result.json.
Return a verdict object with status NICE only if the task is genuinely complete, reproducible, within scope, and supported by verifier evidence.
Return NAUGHTY with concrete issues if anything is missing, fabricated, placeholder-like, out-of-scope, or weakly verified.
Do not share assumptions with reviewer B.
"""
'''

SANTA_REVIEWER_B_TOML = '''name = "autopilot-santa-reviewer-b"
description = "Santa Method reviewer B. Independent adversarial reviewer that challenges the same NodeKit task result from a different angle."
sandbox_mode = "read-only"
developer_instructions = """
You are Santa reviewer B for an Autopilot NodeKit task. Do not edit files.

Independently challenge the task result. Look for hallucinated completion, missing source data, weak provenance, missing outputs, verifier gaps, journal-format drift, hidden broad rewrites, and graph/memory mistakes.
Return NICE only with evidence-backed confidence. Return NAUGHTY with concrete issues and the smallest repair request.
Do not share assumptions with reviewer A.
"""
'''

HOOKS_JSON_EXAMPLE = r'''{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "/bin/sh -lc 'ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd); exec /usr/bin/env python3 \"$ROOT/.codex/hooks/autopilot_stop_render.py\"'",
            "timeout": 30,
            "statusMessage": "Rendering Autopilot NodeKit live manifest"
          }
        ]
      }
    ]
  }
}
'''

STOP_RENDER_HOOK = '''#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        payload = {}
    cwd = Path(payload.get("cwd") or os.getcwd())
    manifest = cwd / "automation" / "manifest.yml"
    if not manifest.exists():
        print(json.dumps({"continue": True, "systemMessage": "Autopilot NodeKit hook skipped: automation/manifest.yml not found."}))
        return 0
    proc = subprocess.run(
        [sys.executable, "-m", "autopilot_nodekit", "render", "--workspace", str(cwd)],
        cwd=str(cwd),
        text=True,
        capture_output=True,
        timeout=25,
    )
    if proc.returncode == 0:
        message = "Autopilot NodeKit live manifest rendered."
    else:
        message = "Autopilot NodeKit render hook failed; inspect automation/ and package installation."
    print(json.dumps({"continue": True, "systemMessage": message}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''

SKILLS: Dict[str, str] = {
    "autopilot-nodekit-loop-contract/SKILL.md": """---
name: autopilot-nodekit-loop-contract
description: Use when turning a vague Codex coding, debugging, CI, benchmarking, reproduction, or experiment task into a bounded Autopilot NodeKit loop with a verifier, state file, graph semantics, and stop conditions.
---

# Autopilot NodeKit Loop Contract

Use this skill before long-running debugging, refactoring, benchmarking, reproduction, CI-fix, research-code, or experiment-automation tasks. For large artifact batches such as journal figures, switch to `$autopilot-review-gated-figure-loop` and enforce human plan review, boundary test, pilot review, and final audit gates.

## 1. Define the loop before editing

Write a short loop contract with:

- Codex `/goal`: render it with `python -m autopilot_nodekit codex-goal --workspace . --task-id <ID>` when the task maps to a NodeKit task.
- Goal: the concrete outcome.
- Scope: files, modules, datasets, or issues included.
- Non-goals: what must not be changed.
- State file: `LOOP_STATE.md` or `PLANS.md`.
- Verifier: exact command, test, benchmark, or artifact check.
- Max iterations: default 3 unless the user asks otherwise.
- Stop condition: success, blocker, repeated failure with no new hypothesis, or scope risk.

## 2. Use NodeKit as outer loop

Autopilot NodeKit is authoritative for task state. Do not bypass it by manually editing `automation/autopilot.sqlite`.

When working inside a claimed task, read:

- `$AUTOPILOT_PROMPT`
- `$AUTOPILOT_CONTEXT_PACK`
- `$AUTOPILOT_VERIFIER_COMMAND`

## 3. Make verifier authoritative

Do not write `status: passed` unless the verifier is expected to pass.

If the verifier fails, write `status: failed` or `blocked` and include evidence from logs.

## 4. Apply graph semantics correctly

Use:

- `depends_on` only when the predecessor must be `passed`.
- `after_attempt` for bridge tasks that should run after a predecessor finishes, even if it failed.
- `blocked_by` for explicit blockers that release after passed/skipped/superseded.
- `parent_id` for lineage.
- `memory.required_task_ids` to force memory inheritance from failed or blocked tasks.

## 5. Iterate safely

For each iteration:

1. Read current state and memory.
2. Choose the smallest defensible next action.
3. Make the patch.
4. Run the verifier or explain why it cannot run.
5. Update `LOOP_STATE.md` / `PLANS.md`.
6. Write `worker_result.json` with status, summary, details, memory nodes, and any graph patch.

## 6. Final result contract

The final worker result must contain:

- status: `passed`, `failed`, `blocked`, or `skipped`
- summary: one-line manifest result
- details: evidence-rich explanation
- memory_nodes: reusable facts, commands, decisions, failures, and artifact paths
- graph_patch: only if the task graph should change
""",
    "autopilot-nodekit-codex-goal/SKILL.md": """---
name: autopilot-nodekit-codex-goal
description: Use when setting or refining a native Codex /goal for an Autopilot NodeKit task, especially to keep the goal under Codex limits while preserving verifier, scope, memory, and stop-condition semantics.
---

# Autopilot NodeKit Codex Goal

Codex owns native `/goal` state in the active Codex thread. NodeKit owns durable external state: task graph, verifier, run artifacts, and memory nodes.

## Goal rendering

Prefer rendering a task-specific goal:

```bash
python -m autopilot_nodekit codex-goal --workspace . --task-id <TASK_ID>
```

Paste the result into Codex CLI/app/IDE.

## Goal requirements

A NodeKit-compatible `/goal` must include:

- task id and objective
- success criteria
- verifier command or first action to define one
- allowed scope and graph safety rules
- memory/state files: `AGENTS.md`, `LOOP_STATE.md`, `PLANS.md`, `automation/manifest.yml`
- iteration rule
- stop condition

## Important distinction

Do not assume `codex exec` attaches a durable `/goal` to the active interactive thread. Use `/goal` in Codex itself for native Goal mode, then use NodeKit commands as the controlled outer loop.
""",
    "autopilot-nodekit-worker-result/SKILL.md": """---
name: autopilot-nodekit-worker-result
description: Use when writing or reviewing Autopilot NodeKit worker_result.json files, especially to ensure status, verifier evidence, memory nodes, and graph_patch operations are valid.
---

# Autopilot NodeKit Worker Result Contract

A worker must write `$AUTOPILOT_RUN_DIR/worker_result.json` before exiting.

## Required fields

```json
{
  "status": "passed | failed | blocked | skipped",
  "summary": "One-line result for manifest.live.",
  "details": "Full evidence and decisions.",
  "memory_nodes": []
}
```

## Status rules

- `passed`: success criteria satisfied and verifier expected to pass.
- `failed`: attempted work did not satisfy criteria or verifier failed.
- `blocked`: missing input, missing dependency, environment failure, or unsafe next step.
- `skipped`: intentionally not needed, with evidence.

The verifier is authoritative. A pass-like result will be overridden by NodeKit if the worker command or verifier exits non-zero.

## Memory node rules

Create memory nodes for reusable facts:

- exact setup/test/build commands
- failure modes and root causes
- file/module decisions
- API or schema contracts
- blocker evidence

Each node should include `title`, `scope`, `tags`, `content`, `raw_artifacts`, and `confidence`.

## Graph patch rules

Use `graph_patch.operations` for durable task graph changes.

For bridge tasks after a failed parent, do this:

```json
{
  "op": "add_task",
  "task": {
    "id": "T001.1",
    "parent_id": "T001",
    "after_attempt": ["T001"],
    "memory": {"required_task_ids": ["T001"]}
  }
}
```

Do not put `depends_on: ["T001"]` on a bridge that should run after `T001` fails.
""",
    "autopilot-nodekit-graph-curator/SKILL.md": """---
name: autopilot-nodekit-graph-curator
description: Use when reviewing, repairing, or designing Autopilot NodeKit task graphs, including depends_on, after_attempt, blocked_by, supersede_task, and memory inheritance selectors.
---

# Autopilot NodeKit Graph Curator

Use this skill to keep the task graph executable and auditable.

## Edge semantics

- `depends_on`: predecessor must be `passed`.
- `after_attempt`: predecessor must reach any terminal status: `passed`, `failed`, `blocked`, `skipped`, or `superseded`.
- `blocked_by`: predecessor releases this task only after `passed`, `skipped`, or `superseded`.
- `child_of`: lineage only, not a readiness gate.
- `inserted_before`: planning/order hint only, not a readiness gate.
- `supersedes`: history link only, not a readiness gate.

## Bridge task pattern

When task `T001` fails because setup is unknown:

- Insert `T001.1` with `parent_id: T001` and `after_attempt: [T001]`.
- Add `memory.required_task_ids: [T001]`.
- Do not use `depends_on: [T001]` unless `T001` passed.

## Validation checklist

Run:

```bash
python -m autopilot_nodekit validate --workspace .
```

Then check:

- no dangling edges
- no gating cycles
- no planned task waiting forever on a failed `depends_on`
- future tasks have memory selectors for bridge outputs
""",
    "autopilot-nodekit-memory-curator/SKILL.md": """---
name: autopilot-nodekit-memory-curator
description: Use when creating, selecting, or reviewing Autopilot NodeKit structured memory nodes so future Codex runs inherit durable evidence without bloating prompt context.
---

# Autopilot NodeKit Memory Curator

Structured memory nodes are durable evidence pointers, not compressed chat summaries.

## What belongs in memory

Create nodes for:

- exact commands and environment assumptions
- reproducible bugs and root causes
- API, schema, and file contracts
- decisions that affect future tasks
- verifier evidence and artifact paths

Avoid nodes for:

- generic commentary
- unverified guesses
- facts not useful to future tasks

## Non-lossy retrieval pattern

Keep the raw evidence in `runs/<run_id>/` and `memory/nodes/<node_id>/`.

Prompt context should usually receive excerpts plus `node_file` and `raw_artifacts`, not every full node body.

## Future-use cues

Every node should make clear when a future task should load it, what raw artifact to inspect, and what confidence to assign.
""",
    "autopilot-santa-review/SKILL.md": """---
name: autopilot-santa-review
description: Use after each non-human Autopilot NodeKit task before writing a passed worker_result.json; enforces Santa Method dual independent NICE/NICE review.
---

# Autopilot Santa Review

Use this skill for every non-human NodeKit task that might be marked `passed`.

## Rule

A task is not passed until all three are true:

1. The task verifier passes or the task has an explicit blocked/skipped status with evidence.
2. Reviewer A independently returns NICE.
3. Reviewer B independently returns NICE.

If either reviewer returns NAUGHTY, repair the smallest actionable issue, re-run the verifier, and run fresh reviews.

## Reviewer separation

Use repo custom agents when available:

- `autopilot-santa-reviewer-a`
- `autopilot-santa-reviewer-b`

Do not give reviewer B reviewer A's conclusions. Each reviewer should inspect the task contract, changed files, output artifacts, verifier logs, and evidence independently.

## Required worker_result.json field

```json
{
  "review": {
    "policy": "santa_dual_review",
    "reviewer_a": {"agent": "autopilot-santa-reviewer-a", "status": "NICE", "summary": "...", "evidence": ["verifier.log"], "issues": []},
    "reviewer_b": {"agent": "autopilot-santa-reviewer-b", "status": "NICE", "summary": "...", "evidence": ["artifact path"], "issues": []},
    "fixes_after_review": []
  }
}
```

NodeKit will override `passed` to `failed` if the review is required and missing, not produced by the expected reviewer agents, missing evidence, or not NICE/NICE.
""",
    "autopilot-review-gated-figure-loop/SKILL.md": '---\nname: autopilot-review-gated-figure-loop\ndescription: Use for large artifact batches such as 100 journal figures where Codex/NodeKit must generate many tasks, require human plan review, run a boundary test, pilot the first artifact, then loop through the batch with self-correction and final verification.\n---\n\n# Autopilot Review-Gated Figure Loop\n\nUse this skill whenever the user asks for many journal figures, plots, panels, charts, or other repeated deliverables.\n\n## Required five-phase flow\n\n0. Configure Layer 0 files, skills, subagents, permissions, and verifier policy; stop for human review.\n1. Generate a large, explicit task graph and stop for human review.\n2. After approval, run only the boundary/permission test.\n3. Complete Figure 001 as the pilot artifact, then stop for human journal-fit review.\n4. After pilot approval, run the bulk loop with Santa dual-review, repair tasks, and final audit.\n\nDo not skip or soften these gates.\n\n## Generate enough tasks\n\nFor `N` figures/artifacts, do not create a tiny vague task list.\n\nDefault command:\n\n```bash\npython -m autopilot_nodekit generate-figure-plan --workspace . --figures <N> --journal "<journal>" --tasks-per-figure 3\n```\n\nThis creates approximately `3N + 5` tasks:\n\n- one Layer 0 setup-review gate\n- one human plan-review gate\n- one boundary/permission test\n- three tasks per figure: spec, render, QC/self-correction\n- one human pilot-review gate after Figure 001\n- one final audit\n\nFor 100 figures, this should produce 305 tasks by default.\n\n## Human plan review is mandatory\n\nAfter generation:\n\n```bash\npython -m autopilot_nodekit validate --workspace .\npython -m autopilot_nodekit status --workspace .\n```\n\nThen the user must read:\n\n- `TASK_REVIEW.md`\n- `REQUIREMENTS_LOCK.md`\n- `automation/manifest.live.md`\n\nOnly after setup approval and human plan approval:\n\n```bash\npython -m autopilot_nodekit approve-setup --workspace . --summary "Layer 0 setup reviewed and approved."\npython -m autopilot_nodekit approve-plan --workspace . --summary "Plan reviewed and approved."\n```\n\n## Boundary test is mandatory\n\nAfter plan approval, only `H010_BOUNDARY_PERMISSION_TEST` should release. It must prove:\n\n- Codex can read required inputs.\n- Codex writes only inside approved output directories.\n- The verifier command can run.\n- Raw evidence goes into `runs/` and memory nodes.\n\n## Pilot review is mandatory\n\nAfter Figure 001 QC passes, bulk tasks must remain locked until:\n\n```bash\npython -m autopilot_nodekit approve-pilot --workspace . --summary "Figure 001 reviewed and approved for batch loop."\n```\n\nDo not release `F002+` tasks before this approval.\n\n## Per-task interactive Codex dialog\n\nFor human-visible task-by-task execution:\n\n```bash\npython -m autopilot_nodekit codex-prepare --workspace . --worker-id codex-interactive\nbash runs/<run_id>/open_codex.sh\npython -m autopilot_nodekit codex-finish --workspace . --run-id <run_id>\n```\n\nEach prepared task gets a fresh Codex conversation with its own prompt, context pack, verifier contract, memory selection, and required `worker_result.json` path.\n\n## Self-correction rule\n\nBefore a non-human task is marked passed, run Santa dual-review and require NICE/NICE. If a figure fails QC, do not mark it passed. Insert focused repair tasks with `graph_patch`, using `after_attempt` or `depends_on` correctly, and include memory selectors so future tasks inherit the failure evidence.\n',
}


SKILLS["autopilot-project-spec/SKILL.md"] = """---
name: autopilot-project-spec
description: Use when a fuzzy user prompt should become a complete Autopilot NodeKit PROJECT_SPEC.yml before task generation; prefers fast gate mode to avoid excessive manual stops.
---

# Autopilot Project Spec

Use this skill before starting a large Codex/NodeKit loop from a natural-language prompt.

## Purpose

Do not make the user write a long orchestration prompt. Convert the project prompt into `PROJECT_SPEC.yml`, then let NodeKit generate:

- `PROJECT_SETUP.yml`
- `GOAL_CONTRACT.yml`
- `automation/manifest.yml`
- `TASK_REVIEW.md`
- `REQUIREMENTS_LOCK.md`

## Strong commands

Draft a spec only:

```bash
python -m autopilot_nodekit spec-from-prompt --workspace . --prompt-file PROJECT_PROMPT.md --gate-mode fast
```

Start the full loop from prompt:

```bash
python -m autopilot_nodekit start-from-prompt --workspace . --prompt-file PROJECT_PROMPT.md --gate-mode fast --force-codex-native
```

Start from an already edited spec:

```bash
python -m autopilot_nodekit start-from-spec --workspace . --spec PROJECT_SPEC.yml --force-codex-native
```

## Gate mode choice

- `fast`: one startup approval, then automatic boundary test, F001 automatic pilot guard, bulk loop, final audit.
- `balanced`: one startup approval plus human F001 pilot review.
- `strict`: separate setup, plan, and pilot human gates.

Use `fast` unless the user explicitly asks for repeated manual gates or the project is unusually high risk.

## Spec must include

- project name, type, artifact count, journal/target venue
- inputs and missing-input policy
- outputs and per-artifact deliverables
- Definition of Done
- forbidden actions
- permissions and sandbox boundary
- verification commands
- repair policy
- Codex-native files, skills, subagents

No clear spec means no automated loop.
"""

SKILLS["autopilot-review-gated-figure-loop/SKILL.md"] = """---
name: autopilot-review-gated-figure-loop
description: Use for large artifact batches such as 100 journal figures where Codex/NodeKit must generate many tasks, run a boundary test, pilot the first artifact, minimize human stops when requested, then loop with Santa review, repair, and final verification.
---

# Autopilot Figure Loop

Use this skill whenever the user asks for many journal figures, plots, panels, charts, or repeated deliverables.

## Preferred v0.7 startup

Start from a project prompt and let NodeKit draft the spec:

```bash
python -m autopilot_nodekit start-from-prompt --workspace . --prompt-file PROJECT_PROMPT.md --gate-mode fast --force-codex-native
```

If the user wants more review, use `--gate-mode balanced` or `--gate-mode strict`.

## Task scale

For `N` figures/artifacts, do not create a tiny vague task list. With `--tasks-per-figure 3`:

- fast: `3N + 3`
- balanced: `3N + 4`
- strict: `3N + 5`

For 100 figures, fast mode should still produce 303 tasks.

## Human stops

Fast mode has one manual startup approval. After that, do not keep stopping for human review. Use:

- boundary permission test
- verifier authority
- F001_QC automatic pilot guard
- Santa dual-review after each non-human task
- repair tasks on failure
- final audit

Balanced mode adds one human pilot gate. Strict mode keeps setup, plan, and pilot gates.

## Per-task Codex loop

```bash
python -m autopilot_nodekit next-command --workspace .
python -m autopilot_nodekit codex-prepare --workspace . --worker-id codex-interactive
bash runs/<run_id>/open_codex.sh
python -m autopilot_nodekit codex-finish --workspace . --run-id <run_id>
```

Each prepared task gets a fresh Codex conversation with its own prompt, context pack, verifier contract, memory selection, and required `worker_result.json` path.

## Self-correction rule

Before a non-human task is marked passed, run Santa dual-review and require NICE/NICE. If a figure fails QC, do not mark it passed. Insert focused repair tasks with `graph_patch`, using `after_attempt` or `depends_on` correctly, and include memory selectors so future tasks inherit failure evidence.
"""


def install_codex_native_files(workspace: Path, force: bool = False) -> None:
    workspace = workspace.resolve()
    files: Dict[Path, str] = {
        workspace / "AGENTS.md": AGENTS_MD,
        workspace / "LOOP_STATE.md": LOOP_STATE_MD,
        workspace / "PLANS.md": PLANS_MD,
        workspace / ".codex" / "config.toml": CODEX_CONFIG_TOML,
        workspace / ".codex" / "agents" / "autopilot-checker.toml": CHECKER_AGENT_TOML,
        workspace / ".codex" / "agents" / "autopilot-explorer.toml": EXPLORER_AGENT_TOML,
        workspace / ".codex" / "agents" / "autopilot-santa-reviewer-a.toml": SANTA_REVIEWER_A_TOML,
        workspace / ".codex" / "agents" / "autopilot-santa-reviewer-b.toml": SANTA_REVIEWER_B_TOML,
        workspace / ".codex" / "hooks.json": HOOKS_JSON_EXAMPLE,
        workspace / ".codex" / "hooks.json.example": HOOKS_JSON_EXAMPLE,
        workspace / ".codex" / "hooks" / "autopilot_stop_render.py": STOP_RENDER_HOOK,
    }
    for rel, content in SKILLS.items():
        files[workspace / ".agents" / "skills" / rel] = content
    for path, content in files.items():
        if path.exists() and not force:
            continue
        write_text(path, content)
        if path.name.endswith(".py"):
            path.chmod(0o755)

# v0.7 final override kept in sync with repo-local skill.
SKILLS["autopilot-project-spec/SKILL.md"] = '---\nname: autopilot-project-spec\ndescription: Use when a fuzzy user prompt should become a complete Autopilot NodeKit PROJECT_SPEC.yml before task generation; prefers fast gate mode to avoid excessive manual stops.\n---\n\n# Autopilot Project Spec\n\nUse this skill before starting a large Codex/NodeKit loop from a natural-language prompt.\n\n## Purpose\n\nDo not make the user write a long orchestration prompt. Convert the project prompt into `PROJECT_SPEC.yml`, then let NodeKit generate:\n\n- `PROJECT_SETUP.yml`\n- `GOAL_CONTRACT.yml`\n- `automation/manifest.yml`\n- `TASK_REVIEW.md`\n- `REQUIREMENTS_LOCK.md`\n\n## Strong commands\n\nDraft a deterministic spec only:\n\n```bash\npython -m autopilot_nodekit spec-from-prompt --workspace . --prompt-file PROJECT_PROMPT.md --gate-mode fast\n```\n\nAsk Codex to draft/refine the spec from the prompt:\n\n```bash\npython -m autopilot_nodekit codex-draft-spec --workspace . --prompt-file PROJECT_PROMPT.md --gate-mode fast\nbash runs/spec-draft-*/open_codex_spec.sh\n```\n\nStart the full loop from prompt:\n\n```bash\npython -m autopilot_nodekit start-from-prompt --workspace . --prompt-file PROJECT_PROMPT.md --gate-mode fast --force-codex-native\n```\n\nStart from an already edited spec:\n\n```bash\npython -m autopilot_nodekit start-from-spec --workspace . --spec PROJECT_SPEC.yml --force-codex-native\n```\n\n## Gate mode choice\n\n- `fast`: one startup approval, then automatic boundary test, F001 automatic pilot guard, bulk loop, final audit.\n- `balanced`: one startup approval plus human F001 pilot review.\n- `strict`: separate setup, plan, and pilot human gates.\n\nUse `fast` unless the user explicitly asks for repeated manual gates or the project is unusually high risk.\n\n## Spec must include\n\n- project name, type, artifact count, journal/target venue\n- inputs and missing-input policy\n- outputs and per-artifact deliverables\n- Definition of Done\n- forbidden actions\n- permissions and sandbox boundary\n- verification commands\n- repair policy\n- Codex-native files, skills, subagents\n\nNo clear spec means no automated loop.\n'

# v0.8 smart-start/background overrides.
# CODEX_CONFIG_TOML already omits job_max_runtime_seconds in v0.8.

AGENTS_MD += '''

## v0.8 Smart-start trigger rule

If the user says any of the following, treat it as an automatic trigger for Autopilot NodeKit startup, even if their prompt is short:

- "基于 autopilot-nodekit"
- "use autopilot-nodekit"
- "autopilot-nodekit"
- "NodeKit loop"

Do not ask the user to paste the long control-plane prompt. The fixed flow is now built into this package.

Required first action:

```bash
python -m autopilot_nodekit smart-start --workspace . --prompt-file PROJECT_PROMPT.md --force-codex-native
```

If the user has not yet created `PROJECT_PROMPT.md`, create it from the user's latest natural-language request first, then run `smart-start`.

`smart-start` must ask before execution when any required startup setting is missing:

- `gate_mode`: `fast`, `balanced`, or `strict`
- `task_scale`: `smoke`, `standard`, or `prod`
- `artifact_count`
- `target_journal` / target venue for figure projects
- generated deliverables if the requested output files are unclear

Do not silently default `gate_mode` or `task_scale` in the fixed smart-start flow. If these settings are unclear, write/read `START_QUESTIONS.md` and wait for user answers.

Task scale controls graph density:

- `smoke`: 2 tasks/artifact, intended for quick verification and still at least one task per artifact.
- `standard`: 3 tasks/artifact, the default production balance.
- `prod`: 4 tasks/artifact with a separate journal/compliance check.

Background execution must use backend detection instead of assuming tmux:

```bash
python -m autopilot_nodekit background-doctor --workspace .
python -m autopilot_nodekit launch-background --workspace . --worker-id codex-worker --max-cycles 0
```

`--max-cycles 0` means no NodeKit cycle limit. NodeKit defaults do not impose wall-clock timeouts on background worker/verifier commands.

Layer commands:

- Goal/contract: `project-spec-review`, `contract-review`, `codex-contract-goal`
- Task manifest/DAG: `review-plan`, `validate --strict`, `status`
- Execution loop: `codex-prepare`, run `runs/<run_id>/open_codex.sh`, `codex-finish`
- Memory/state: `memory-plan`, `memory-search`, `replay-run`
- Verification: `verify-artifact`, `validate --strict`, verifier logs in `runs/<run_id>/verifier.log`
- Repair: `add-repair-task`, then `codex-prepare` and `codex-finish`
- Human gate: `approve-start`, `approve-setup`, `approve-plan`, `approve-pilot`, `approve-task`, `reject-task`
- Observability: `metrics`, `replay-run`, `automation/events.jsonl`, `automation/manifest.live.md`
'''

SKILLS["autopilot-smart-start/SKILL.md"] = '''---
name: autopilot-smart-start
description: Use whenever the user mentions autopilot-nodekit or asks to run a prompt through this package. Converts the user prompt into startup files, asks missing settings, and starts only after required settings are resolved.
---

# Autopilot Smart Start

This is the mandatory first skill when the user says "基于 autopilot-nodekit" or otherwise asks to use this package.

## Fixed flow

1. Create or update `PROJECT_PROMPT.md` from the user's actual task prompt.
2. Run:

```bash
python -m autopilot_nodekit smart-start --workspace . --prompt-file PROJECT_PROMPT.md --force-codex-native
```

3. If `START_QUESTIONS.md` is produced, stop and ask the user only those missing settings. Do not start the task graph.
4. After the user answers, write `START_ANSWERS.yml` with `confirmed: true`, then rerun smart-start.
5. Once the graph exists, follow only:

```bash
python -m autopilot_nodekit next-command --workspace .
```

## Do not silently guess these fields

- `gate_mode`: fast / balanced / strict
- `task_scale`: smoke / standard / prod
- `artifact_count`
- `target_journal` or target venue for figure projects
- generated deliverables if file outputs are unclear

## Gate modes

- `fast`: startup approval, boundary test, automatic F001 pilot guard, bulk loop, final audit.
- `balanced`: startup approval, boundary test, human F001 pilot review, bulk loop, final audit.
- `strict`: separate setup review, plan review, boundary test, human F001 pilot review, bulk loop, final audit.

## Task scales

- `smoke`: 2 tasks/artifact.
- `standard`: 3 tasks/artifact.
- `prod`: 4 tasks/artifact including separate compliance check.

## Background policy

Do not assume tmux. Run:

```bash
python -m autopilot_nodekit background-doctor --workspace .
python -m autopilot_nodekit launch-background --workspace . --worker-id codex-worker --max-cycles 0
```

`--max-cycles 0` means unlimited cycles. Do not add wall-clock timeout limits to background workers unless the user explicitly asks.
'''

SKILLS["autopilot-project-spec/SKILL.md"] = '''---
name: autopilot-project-spec
description: Use when a fuzzy user prompt should become a complete Autopilot NodeKit PROJECT_SPEC.yml before task generation; v0.8 requires asking missing startup settings instead of silently guessing.
---

# Autopilot Project Spec

Use this skill after `$autopilot-smart-start` determines the project is ready to convert into a spec.

## Required behavior

Do not make the user write a long orchestration prompt. Convert the project prompt into `PROJECT_SPEC.yml`, then let NodeKit generate:

- `PROJECT_SETUP.yml`
- `GOAL_CONTRACT.yml`
- `automation/manifest.yml`
- `TASK_REVIEW.md`
- `REQUIREMENTS_LOCK.md`

But do not start execution if these are missing or ambiguous:

- `gate_mode`: fast / balanced / strict
- `task_scale`: smoke / standard / prod
- artifact count
- target journal / venue
- deliverable file types if unclear

Use `smart-start` as the primary command:

```bash
python -m autopilot_nodekit smart-start --workspace . --prompt-file PROJECT_PROMPT.md --force-codex-native
```

If questions are required, NodeKit writes:

- `START_QUESTIONS.md`
- `START_ANSWERS.yml.template`

After answers:

```bash
python -m autopilot_nodekit smart-start --workspace . --prompt-file PROJECT_PROMPT.md --answers START_ANSWERS.yml --force-codex-native
```

## Spec must include

- project name, type, artifact count, journal/target venue
- gate mode and task scale
- inputs and missing-input policy
- outputs and per-artifact deliverables
- Definition of Done
- forbidden actions
- permissions and sandbox boundary
- verification commands
- repair policy
- Codex-native files, skills, subagents
- background backend/timeout policy

No clear spec means no automated loop.
'''

SKILLS["autopilot-review-gated-figure-loop/SKILL.md"] += '''

## v0.8 task scale and startup rules

Use `smart-start` first for all natural-language prompts. Do not silently default gate mode or task scale in the fixed flow.

Task scale controls per-figure graph density:

- `smoke`: 2 tasks per figure, about `2N + gates` total tasks.
- `standard`: 3 tasks per figure, about `3N + gates` total tasks.
- `prod`: 4 tasks per figure, about `4N + gates` total tasks with separate journal/compliance check.

For 100 figures in fast mode:

- smoke ≈ 203 tasks
- standard ≈ 303 tasks
- prod ≈ 403 tasks

Use background detection before launching long loops:

```bash
python -m autopilot_nodekit background-doctor --workspace .
python -m autopilot_nodekit launch-background --workspace . --worker-id codex-worker --max-cycles 0
```
'''
