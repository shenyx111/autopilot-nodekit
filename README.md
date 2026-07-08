# Autopilot NodeKit v0.8.0

[中文](#中文) | [English](#english)

Autopilot NodeKit is a local control plane for running Codex against large, repeatable work. It turns a broad request into a project spec, task graph, verifier checks, review gates, repair loops, memory records, and audit logs.

The v0.8 release focuses on startup. You no longer need to paste a long control prompt every time. Give Codex your task, mention `autopilot-nodekit`, and let the smart-start flow create the project files it needs.

## English

### Good fit

Use NodeKit when a task is too large or too sensitive for one long prompt:

- generating many paper figures or report figures;
- cleaning, converting, or organizing batches of files;
- producing scripts and checking their outputs;
- fixing code, adding tests, and keeping verifier evidence;
- resuming work after interruption with a clear history.

### Example prompt

```text
Use autopilot-nodekit for this task:
Create 100 publication-ready figures for a Nature-style paper.
The input data is in data/. Each figure must include source-data notes,
a plotting script, PDF/PNG/SVG outputs, a caption, and QC evidence.
Do not fabricate data, do not use placeholder figures, and do not modify raw data.
Run as automatically as possible, but ask me first if key settings are missing.
```

### Smart start

Start from a prompt file:

```bash
python -m autopilot_nodekit smart-start \
  --workspace . \
  --prompt-file PROJECT_PROMPT.md \
  --force-codex-native
```

When required settings are missing, NodeKit writes:

```text
START_QUESTIONS.md
START_ANSWERS.yml.template
```

Fill the answers, set `confirmed: true`, then rerun:

```bash
python -m autopilot_nodekit smart-start \
  --workspace . \
  --prompt-file PROJECT_PROMPT.md \
  --answers START_ANSWERS.yml \
  --force-codex-native
```

### Settings NodeKit asks you to confirm

- `gate_mode`: `fast`, `balanced`, or `strict`
- `task_scale`: `smoke`, `standard`, or `prod`
- `artifact_count`
- target journal or target venue
- deliverables, if the prompt leaves them unclear

### Gate modes

- `fast`: one startup approval, a boundary test, automatic F001 pilot guard, bulk loop, final audit.
- `balanced`: one startup approval, a boundary test, human F001 pilot review, bulk loop, final audit.
- `strict`: setup review, plan review, boundary test, human F001 pilot review, bulk loop, final audit.

All modes keep the same quality floor: verifier checks, Santa dual review, repair loops, evidence, memory, logs, and final audit.

### Task scales

- `smoke`: 2 tasks per artifact.
- `standard`: 3 tasks per artifact.
- `prod`: 4 tasks per artifact, including a separate journal or compliance check.

For 100 figures in fast mode, this means roughly 203, 303, or 403 tasks.

### Background execution

Check the available background backend first:

```bash
python -m autopilot_nodekit background-doctor --workspace .
```

Launch the best available backend:

```bash
python -m autopilot_nodekit launch-background \
  --workspace . \
  --worker-id codex-worker \
  --max-cycles 0
```

`--max-cycles 0` means unlimited NodeKit cycles. Worker and verifier commands do not get a NodeKit wall-clock timeout unless you add one.

### Main loop

After startup, ask NodeKit for the next command:

```bash
python -m autopilot_nodekit next-command --workspace .
```

For an interactive Codex dialog on one task:

```bash
python -m autopilot_nodekit codex-prepare --workspace . --worker-id codex-interactive
bash runs/<run_id>/open_codex.sh
python -m autopilot_nodekit codex-finish --workspace . --run-id <run_id>
```

### Verification

```bash
python -m compileall -q autopilot_nodekit tests
python -m pytest -q
python -m autopilot_nodekit validate --workspace . --strict
```

See `docs/SMART_START_BACKGROUND.md` for the full layer-to-command map.

---

## 中文

Autopilot NodeKit 是给 Codex 用的本地任务控制面。它把一个大目标拆成项目规范、目标契约、任务清单、验证规则、审核记录和运行日志，让 Codex 一次处理一个边界清楚的任务。

v0.8 的重点是启动体验。你不用再记一大段控制提示词。把需求告诉 Codex，提到 `autopilot-nodekit`，smart-start 流程会生成项目文件，并在关键信息缺失时先问清楚。

### 适合的任务

NodeKit 适合这类需要批量执行、可恢复、可审计的工作：

- 批量生成论文图、报告图、数据分析图；
- 批量整理文件、转换格式、生成脚本；
- 批量修复代码、补测试、跑验证；
- 中断后继续运行；
- 失败后保留证据，再进入修复流程。

### 示例：制作 100 张期刊图

可以给 Codex 这样的需求：

```text
基于 autopilot-nodekit 完成以下任务：
为一篇 Nature 风格论文制作 100 张 publication-ready figures。
输入数据在 data/ 目录。每张图必须有源数据记录、绘图脚本、
PDF/PNG/SVG、caption 和 QC evidence。
禁止伪造数据，禁止占位图，禁止直接修改 raw data。
希望尽量自动运行；缺少关键设置时先问我。
```

NodeKit 会先生成这些启动文件：

```text
PROJECT_PROMPT.md          # 用户需求
PROJECT_SPEC.draft.yml     # 项目规范草案
PROJECT_SPEC.md            # 人类可读项目规范
START_QUESTIONS.md         # 缺失设置时的问题
START_ANSWERS.yml.template # 用户填写的答案模板
```

如果 prompt 没说清 gate mode、任务规模、图数量、目标期刊或数据目录，系统会先把问题列出来。你确认后，再生成任务图。

### 三种审核模式

```text
fast      人工停顿最少，适合需求清楚、想尽快跑起来的任务。
balanced  先做第一个完整样例并人工确认，适合大多数科研任务。
strict    先审核 setup、目标契约、任务清单和 pilot，适合高风险任务。
```

三种模式都会保留 verifier、Santa dual review、evidence、memory、log 和 final audit。区别主要在人工 gate 的数量。

### 三种任务规模

```text
smoke     每个产物拆成较少任务，用于快速试跑。
standard  默认平衡规模。
prod      拆得更细，适合正式批量生产。
```

例如 100 张图，`prod` 模式大约会生成 400 个任务。任务拆得细一些，恢复、审计和纠错都更稳。

### 任务如何判定完成

Codex 每次完成任务后，需要留下这些材料：

1. 输出文件或修改证据；
2. verifier 检查结果；
3. Santa dual review，两名 reviewer 都给出 NICE；
4. memory、evidence、log 记录；
5. 失败时进入 repair loop。

控制面以 verifier 和 review 为准。worker 自己说 passed，但检查没过，任务会被标记为 failed。

### Token 和成本监控

Santa 双审核和 repair loop 会增加 token 消耗。正式批量运行前，建议先做一次小规模试跑：

```text
1. 用 smoke 规模跑一轮；
2. 看每个任务平均 token、运行时间和失败次数；
3. 再切到 standard 或 prod；
4. 给超长任务补更清楚的 done_when 和 verifier，减少无效迭代。
```

重点关注：

```text
- 每个任务平均重试次数；
- Santa review 触发次数；
- repair loop 次数；
- final audit 失败项；
- token、时间、成本是否集中在少数任务类型。
```

### 常用命令

检查可用后台方式：

```bash
python -m autopilot_nodekit background-doctor --workspace .
```

从 prompt 启动：

```bash
python -m autopilot_nodekit smart-start \
  --workspace . \
  --prompt-file PROJECT_PROMPT.md \
  --force-codex-native
```

查看下一步：

```bash
python -m autopilot_nodekit next-command --workspace .
```

启动后台 loop：

```bash
python -m autopilot_nodekit launch-background \
  --workspace . \
  --worker-id codex-worker \
  --max-cycles 0
```

`--max-cycles 0` 表示不设置 NodeKit 层面的循环次数上限。质量控制交给 verifier、review、repair 和 final audit。

### 一句话说明

Autopilot NodeKit 让 Codex 按任务图、验证器、审核和日志运行。它更适合需要批量完成、失败可修、过程可查的工作。
