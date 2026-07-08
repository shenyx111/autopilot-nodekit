---
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
