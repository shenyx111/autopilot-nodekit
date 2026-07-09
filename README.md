# Autopilot NodeKit v0.9.1

[中文](#中文) | [English](#english)

## 中文

Autopilot NodeKit 是给 Codex 长时间干活用的本地控制层。你给它一个目标，它会把项目说明、完成标准、任务图、验证规则、后台执行、失败修复和最终审计都落到 workspace 里。就算换窗口、进程重启，任务也能接着往下走。

这个 v0.9.1 包可以直接放到 GitHub。它带好 smart-start、后台 worker、运行包装器、后台烟测、heartbeat 日志、stale run 恢复、repair 通过后的图释放命令，以及 verifier/bootstrap 的 shell-safety lint。

状态：experimental but usable。建议先从小项目或 smoke run 开始，再交给昂贵计算或大批量任务。

### 它适合什么任务

- 科研 notebook、Matlantis、ASE 工作流；
- VASP、DFT、SevenNet 数据生成和 fine-tuning；
- AI 可控的有限元计算，例如 COMSOL 参数扫描、仿真批处理和结果整理；
- RAGFlow + 本地 LLM 知识库；
- 批量论文图、数据处理、代码修复；
- 需要长时间运行、断点续跑、保留证据的多阶段项目。

### 它保存哪些状态

NodeKit 会把关键状态写进 workspace：

```text
PROJECT_SPEC.yml          # 项目是什么
GOAL_CONTRACT.yml         # 什么叫完成
automation/manifest.yml   # 任务图
automation/events.jsonl   # 审计事件
automation/autopilot.sqlite
runs/                     # 每个任务的 prompt、输出和证据
memory/nodes/             # 长期记忆和原始材料指针
```

换一个 Codex 窗口，也可以用 `status` 和 `next-command` 接着做。

### 最简单的使用方式

写一个项目需求：

```bash
cat > PROJECT_PROMPT.md <<'EOF'
基于 autopilot-nodekit 完成以下任务：
我要建立一个 RAGFlow + 本地 LLM 的科研知识库。
请先问清缺失设置，再开始任务。使用 balanced gate 和 prod task scale。
EOF
```

启动：

```bash
python -m autopilot_nodekit smart-start \
  --workspace . \
  --prompt-file PROJECT_PROMPT.md \
  --force-codex-native
```

如果信息不够，它会生成：

```text
START_QUESTIONS.md
START_ANSWERS.yml.template
```

填完答案，把 `confirmed: true` 写上，再重新运行 smart-start。

之后最重要的命令只有一个：

```bash
python -m autopilot_nodekit next-command --workspace .
```

### 给 AI agent 的启动提示

如果你把这个 zip 交给 Codex、Claude Code、Cursor 或其他 AI agent，可以直接给它这段话：

```text
请解压 autopilot-nodekit-v0.9.1-open-source-github.zip，进入解压后包含 pyproject.toml 的目录。
用 Python 3.10+ 安装这个工具包：

python -m pip install -e ".[dev]"

然后进入我要自动化的项目 workspace，创建 PROJECT_PROMPT.md，写清楚目标、输入数据、输出要求、限制条件和哪些步骤需要先问我。
运行：

python -m autopilot_nodekit smart-start --workspace . --prompt-file PROJECT_PROMPT.md --force-codex-native

如果生成 START_QUESTIONS.md，请先让我回答。把答案写进 START_ANSWERS.yml，并设置 confirmed: true，再重新运行 smart-start。

之后用下面这个命令查看下一步：

python -m autopilot_nodekit next-command --workspace .

请按 NodeKit 给出的任务图、gate 和 verifier 继续执行。遇到 startup gate、资源 gate、昂贵计算、权限不清楚或 final audit 时先停下来问我。
```

### 第一次运行后会发生什么

第一次 `smart-start` 会先判断信息够不够：

- 信息够用时，它会写入 `PROJECT_SPEC.yml`、`GOAL_CONTRACT.yml`、`automation/manifest.yml` 和第一批任务；
- 信息不够时，它会生成 `START_QUESTIONS.md` 和 `START_ANSWERS.yml.template`，等你补完答案再继续；
- `next-command` 会告诉 agent 当前应该执行哪一步，以及需要留下哪些证据；
- 后台模式会生成 `.nodekit/`、`automation/events.jsonl`、heartbeat 文件和日志；
- verifier 只应该做只读检查。Slurm、COMSOL 批处理、DFT 提交、删除文件这类高风险动作会被 gate 或 shell-safety lint 拦住；
- 如果窗口关了、token 用完了或 worker 中断，可以用 `status`、`next-command` 和 `recover-stale` 接着恢复。

### 后台连续运行

先检查后台能力：

```bash
python -m autopilot_nodekit background-doctor --workspace .
```

启动后台 worker：

```bash
python -m autopilot_nodekit launch-background \
  --workspace . \
  --worker-id codex-worker \
  --max-cycles 0
```

`--max-cycles 0` 表示不限制 NodeKit 循环次数。它不会绕过 Codex/token 限制，只是让 NodeKit 不主动停。

监控：

```bash
python -m autopilot_nodekit status --workspace .
python -m autopilot_nodekit background-status --workspace . --worker-id codex-worker
tail -f automation/events.jsonl
```

### 什么时候需要你介入

后台 loop 正常跑时，不需要每个任务都问你。通常只在这些情况需要你判断：

- startup gate；
- 权限或路径不清楚；
- balanced / strict 模式下第一个 pilot；
- 连续 repair 失败；
- 要提交昂贵计算任务，例如 Slurm / DFT；
- final audit。

其他普通任务应该自动继续。

### 中断后怎么续上

如果 Codex 窗口关了、token 用完了、worker 挂了，先看状态：

```bash
python -m autopilot_nodekit background-status --workspace . --worker-id codex-worker
python -m autopilot_nodekit status --workspace .
python -m autopilot_nodekit next-command --workspace .
```

如果 run 卡住：

```bash
python -m autopilot_nodekit recover-stale --workspace . --age-minutes 30
```

确认某个 run 已经 stale 后：

```bash
python -m autopilot_nodekit recover-stale --workspace . --run-id <RUN_ID> --mark-failed
```

如果 repair 已经通过，但父任务还卡住：

```bash
python -m autopilot_nodekit resolve-by-repair \
  --workspace . \
  --failed-task-id <FAILED_TASK> \
  --repair-task-id <PASSED_REPAIR_TASK>
```

### 三个模式怎么选

```text
fast      停得少，适合需求非常明确的任务。
balanced  推荐默认；先做一个 pilot，人看一次，再批量 loop。
strict    停得多，适合高风险或第一次跑的项目。
```

### Shell 安全加固

v0.9.1 增加了 verifier/bootstrap shell-safety lint。它会拦截 verifier 里容易误执行的 shell 写法，以及 `sbatch`、`srun`、`scancel`、`qsub`、`rm -rf` 等高风险命令。Slurm 提交和取消应该放在显式任务和人工/资源 gate 中；verifier 只做只读检查。

预检查命令：

```bash
python -m autopilot_nodekit shell-safety-lint --command "python -m pytest -q"
```

### GitHub 开源包内容

这个包已经整理为 GitHub 友好版本，包含：

```text
MIT License
NOTICE
.gitattributes
.gitignore
CONTRIBUTING.md
SECURITY.md
CODE_OF_CONDUCT.md
GitHub Actions CI
Issue / PR templates
OPEN_SOURCE_MANIFEST.txt
RELEASE_NOTES.md
```

不要提交真实运行数据和私密信息，例如：

```text
runs/
logs/
automation/autopilot.sqlite
memory/nodes/
START_ANSWERS.yml
.env*
API key
Slurm 输出
真实私有数据
```

### 本地验证

发布前建议运行：

```bash
python -m pip install -e '.[dev]'
python -m compileall -q autopilot_nodekit tests
python -m pytest -q
```

更多说明见：

- `docs/GITHUB_PUBLISHING.md`
- `docs/PUBLIC_QUICKSTART.zh-CN.md`
- `docs/V09_BOOTSTRAP_HARDENING.md`

---

## English

Autopilot NodeKit is a local control layer for long-running Codex work. You give it a goal, and it keeps the project spec, done criteria, task graph, verifier rules, background execution, repair path, durable memory, and final audit in the workspace. If the Codex session changes or a worker restarts, the project still has enough state to continue.

This v0.9.1 package is ready to put in a GitHub repository. It includes smart start, background workers, runtime wrappers, backend smoke checks, heartbeat logs, stale-run recovery, repair-based graph release, and verifier/bootstrap shell-safety lint.

Status: experimental but usable. Start with a small project or smoke run before trusting it with expensive compute.

### Good fit

- Research notebooks, Matlantis, and ASE workflows.
- VASP, DFT, SevenNet data generation, and fine-tuning pipelines.
- AI-controllable finite-element workflows, such as COMSOL parameter sweeps, simulation batches, and result collection.
- RAGFlow + local LLM knowledge bases.
- Batch figure generation, data processing, and code repair.
- Long-running staged projects that need recovery and evidence.

### What state NodeKit keeps

NodeKit writes durable state into the workspace:

```text
PROJECT_SPEC.yml          # what the project is
GOAL_CONTRACT.yml         # what done means
automation/manifest.yml   # task graph
automation/events.jsonl   # audit trail
automation/autopilot.sqlite
runs/                     # per-task prompts, outputs, evidence
memory/nodes/             # durable memory and raw artifact pointers
```

A new Codex session can read the workspace and continue from `status` and `next-command`.

### The simplest way to use it

Create a project prompt:

```bash
cat > PROJECT_PROMPT.md <<'EOF'
Build a local RAGFlow + local LLM knowledge base for my research files.
Use autopilot-nodekit. Ask me for missing settings before starting.
Prefer balanced gates and production task scale.
EOF
```

Run smart start:

```bash
python -m autopilot_nodekit smart-start \
  --workspace . \
  --prompt-file PROJECT_PROMPT.md \
  --force-codex-native
```

If settings are missing, NodeKit writes:

```text
START_QUESTIONS.md
START_ANSWERS.yml.template
```

Fill the answers, set `confirmed: true`, and rerun smart-start.

Then use one control command:

```bash
python -m autopilot_nodekit next-command --workspace .
```

### Prompt for an AI agent

If you give this zip to Codex, Claude Code, Cursor, or another AI agent, you can paste this instruction:

```text
Unzip autopilot-nodekit-v0.9.1-open-source-github.zip, then enter the extracted folder that contains pyproject.toml.
Install the toolkit with Python 3.10+:

python -m pip install -e ".[dev]"

Then go to the project workspace I want to automate. Create PROJECT_PROMPT.md with the goal, input data, output requirements, constraints, and any steps that should ask me first.
Run:

python -m autopilot_nodekit smart-start --workspace . --prompt-file PROJECT_PROMPT.md --force-codex-native

If START_QUESTIONS.md is created, ask me for answers first. Write them into START_ANSWERS.yml, set confirmed: true, and rerun smart-start.

After that, use this command to see the next step:

python -m autopilot_nodekit next-command --workspace .

Continue by following the NodeKit task graph, gates, and verifiers. Stop and ask me at startup gates, resource gates, expensive compute steps, unclear permissions, and final audit.
```

### What happens after the first run

The first `smart-start` checks whether the project has enough information:

- If it has enough, NodeKit writes `PROJECT_SPEC.yml`, `GOAL_CONTRACT.yml`, `automation/manifest.yml`, and the first task batch.
- If details are missing, NodeKit creates `START_QUESTIONS.md` and `START_ANSWERS.yml.template`, then waits for confirmed answers.
- `next-command` tells the agent what to do next and what evidence to leave behind.
- Background mode creates `.nodekit/`, `automation/events.jsonl`, heartbeat files, and logs.
- Verifiers should stay read-only. High-risk actions such as Slurm jobs, COMSOL batches, DFT submission, and file deletion are routed through gates or blocked by shell-safety lint.
- If a window closes, tokens run out, or a worker stops, use `status`, `next-command`, and `recover-stale` to continue.

### Background loop

Check your backend first:

```bash
python -m autopilot_nodekit background-doctor --workspace .
```

Start one worker:

```bash
python -m autopilot_nodekit launch-background \
  --workspace . \
  --worker-id codex-worker \
  --max-cycles 0
```

`--max-cycles 0` means "keep looping". It does not bypass Codex, token, or service limits; it only avoids a NodeKit cycle cap.

Monitor:

```bash
python -m autopilot_nodekit status --workspace .
python -m autopilot_nodekit background-status --workspace . --worker-id codex-worker
tail -f automation/events.jsonl
```

### When humans should step in

Normal background tasks should continue without asking every time. Human judgment is usually needed for:

- startup gates;
- unclear permissions or paths;
- the first pilot in balanced / strict mode;
- repeated repair failures;
- expensive compute submission, such as Slurm or DFT;
- final audit.

### Recover after interruption

If the Codex window closes, tokens run out, or a worker dies, inspect status:

```bash
python -m autopilot_nodekit background-status --workspace . --worker-id codex-worker
python -m autopilot_nodekit status --workspace .
python -m autopilot_nodekit next-command --workspace .
```

If a run is stuck:

```bash
python -m autopilot_nodekit recover-stale --workspace . --age-minutes 30
```

If a run is confirmed stale:

```bash
python -m autopilot_nodekit recover-stale --workspace . --run-id <RUN_ID> --mark-failed
```

If a repair passed but the failed parent still blocks the graph:

```bash
python -m autopilot_nodekit resolve-by-repair \
  --workspace . \
  --failed-task-id <FAILED_TASK> \
  --repair-task-id <PASSED_REPAIR_TASK>
```

### Gate modes

```text
fast      Fewer stops, best for well-scoped work.
balanced  Recommended default; run one pilot, review it, then batch.
strict    More checkpoints, best for high-risk or first-time projects.
```

### Shell-safety hardening

v0.9.1 adds verifier/bootstrap shell-safety lint. It blocks risky verifier patterns and mutating commands such as `sbatch`, `srun`, `scancel`, `qsub`, and `rm -rf`. Slurm submit/cancel actions belong in explicit tasks with human or resource gates; verifiers should stay read-only.

Precheck a command:

```bash
python -m autopilot_nodekit shell-safety-lint --command "python -m pytest -q"
```

### GitHub release contents

This bundle is ready for a GitHub repository and includes:

```text
MIT License
NOTICE
.gitattributes
.gitignore
CONTRIBUTING.md
SECURITY.md
CODE_OF_CONDUCT.md
GitHub Actions CI
Issue / PR templates
OPEN_SOURCE_MANIFEST.txt
RELEASE_NOTES.md
```

Do not commit real runtime state or private data:

```text
runs/
logs/
automation/autopilot.sqlite
memory/nodes/
START_ANSWERS.yml
.env*
API keys
Slurm outputs
private source data
```

### Local verification

Before publishing, run:

```bash
python -m pip install -e '.[dev]'
python -m compileall -q autopilot_nodekit tests
python -m pytest -q
```

More documentation:

- `docs/GITHUB_PUBLISHING.md`
- `docs/PUBLIC_QUICKSTART.zh-CN.md`
- `docs/V09_BOOTSTRAP_HARDENING.md`
