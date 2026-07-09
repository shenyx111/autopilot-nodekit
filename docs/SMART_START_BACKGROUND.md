# Smart-start and background execution

This note is for maintainers and agent implementers. Public users should start from `README.md`, paste the agent instruction block into their AI agent, and let the agent run NodeKit.

NodeKit keeps `autopilot-nodekit` as a fixed startup flow and hardens the path into background loop execution. It avoids forcing non-figure projects through the journal-figure template, installs `.nodekit` runtime wrappers, checks the background backend before startup approval, and lets the v0.9.3 operator handle routine repair, recovery, and repair resolution.

## Trigger phrase

If a user says:

```text
基于 autopilot-nodekit 包里的逻辑，完成以下任务：...
```

or mentions `autopilot-nodekit`, the agent should not ask the user to paste the long control prompt. It should create `PROJECT_PROMPT.md` from the user task and run:

```bash
python -m autopilot_nodekit smart-start --workspace . --prompt-file PROJECT_PROMPT.md --force-codex-native
```

## Required questions before starting

`smart-start` must ask before starting if any of these are unclear:

- `gate_mode`: `fast`, `balanced`, or `strict`
- `task_scale`: `smoke`, `standard`, or `prod`
- `artifact_count`
- `target_journal` or target venue
- generated deliverables if output files are unclear

If missing, it writes:

```text
START_QUESTIONS.md
START_ANSWERS.yml.template
```

Then fill:

```bash
cp START_ANSWERS.yml.template START_ANSWERS.yml
# edit values and set confirmed: true
python -m autopilot_nodekit smart-start --workspace . --prompt-file PROJECT_PROMPT.md --answers START_ANSWERS.yml --force-codex-native
```

## Gate mode strength

- `fast`: one startup approval, boundary test, automatic F001 pilot guard, bulk loop, final audit.
- `balanced`: one startup approval, boundary test, human first-artifact pilot review, bulk loop, final audit.
- `strict`: setup review, plan review, boundary test, human first-artifact pilot review, bulk loop, final audit.

Automatic quality controls are not weakened by `fast`: verifier, Santa dual review, repair loop, evidence, memory, logs, and final audit remain mandatory.

## Task scale strength

For `N` figures/artifacts/workflow stages:

- `smoke`: about `2N + gates` tasks. Uses spec + build/QC per artifact.
- `standard`: about `3N + gates` tasks. Uses spec + build + QC per artifact.
- `prod`: about `4N + gates` tasks. Uses spec + build + validation/compliance + QC per artifact.

For 100 figures in fast mode:

- `smoke`: about 203 tasks.
- `standard`: about 303 tasks.
- `prod`: about 403 tasks.

For non-figure science projects, set `project.type` explicitly, for example `matlantis_workflow`, `materials_dft_sevennet`, `rag_local_llm`, or `science_workflow`. This prevents demo/figure template contamination.

## Background execution

Do not assume tmux because Windows often does not have it. First run:

```bash
python -m autopilot_nodekit background-doctor --workspace .
```

Then run:

```bash
python -m autopilot_nodekit launch-background --workspace . --worker-id codex-worker --max-cycles 0
```

`--max-cycles 0` means NodeKit does not set a cycle limit. The worker keeps iterating until it hits a gate, an error, or an external limit. NodeKit defaults do not impose wall-clock timeouts on worker or verifier commands.

The background worker runs with operator automation enabled by default. When there is no ready task, the operator may add a focused repair task, resolve a failed parent from a passed repair, recover a stale run, or release downstream work. It must not approve human gates, delete files, submit expensive compute, use credentials, or change remote repositories.

## Layer command map

- Layer 0 setup/capability: `setup-review`, `approve-start` or `approve-setup`, `background-doctor`.
- Goal/contract: `project-spec-review`, `contract-review`, `codex-contract-goal`.
- Task manifest/DAG: `review-plan`, `status`, `validate --strict`.
- Execution loop: `worker-loop` or `launch-background`; `codex-prepare` / `codex-finish` are for manual debugging or pilot inspection.
- State/memory: `memory-plan`, `memory-search`, `replay-run`.
- Verification: `verify-artifact`, `validate --strict`, inspect `runs/<run_id>/verifier.log`.
- Repair/reflection: routine `add-repair-task`, `resolve-by-repair`, and `recover-stale` are operator actions. Stop for human review only after repeated failures or a safety gate.
- Human gates: `approve-start`, `approve-setup`, `approve-plan`, `approve-pilot`, `approve-task`, `reject-task`.
- Observability: `metrics`, `automation/events.jsonl`, `automation/manifest.live.md`, `replay-run`.

## One-line agent instruction

```text
基于 autopilot-nodekit 包里的固定流程，完成以下任务：<你的任务>。请先把我的任务写入 PROJECT_PROMPT.md，然后运行 smart-start；如果 START_QUESTIONS.md 出现，只问我里面缺失的设置，不要开始任务；设置确认后生成 PROJECT_SPEC.yml、Goal Contract 和 Task Manifest。后台模式下请运行 background-doctor 和 launch-background，让 worker-loop 与 operator 按任务图、gate、verifier、repair 和恢复逻辑继续。
```

## v0.9 bootstrap hardening

Before approving `G000_START_REVIEW`, run:

```bash
python -m autopilot_nodekit background-doctor --workspace .
python -m autopilot_nodekit validate --workspace . --strict
```

Do not approve startup if `background-doctor` reports an empty worker command, Python import failure, invalid Codex config, platform-incompatible hook, or failed tmux smoke test.

After approval, start exactly one background worker:

```bash
python -m autopilot_nodekit launch-background --workspace . --worker-id codex-worker --max-cycles 0
```

Use these commands only when inspecting the control plane manually. In normal background mode the operator handles routine recovery and repair resolution:

```bash
python -m autopilot_nodekit background-status --workspace . --worker-id codex-worker
python -m autopilot_nodekit recover-stale --workspace . --run-id <RUN_ID> --mark-failed
python -m autopilot_nodekit resolve-by-repair --workspace . --failed-task-id <FAILED> --repair-task-id <PASSED_REPAIR>
```
