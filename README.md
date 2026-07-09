# Autopilot NodeKit v0.9.1

[中文](#中文) | [English](#english)

## 中文

Autopilot NodeKit 是给 Codex 长时间干活用的本地控制层。你给它一个目标，它会把项目说明、完成标准、任务图、验证规则、后台执行、失败修复和最终审计都落到 workspace 里。就算换窗口、进程重启，任务也能接着往下走。

这个包已经整理成可以直接发布到 GitHub 的项目。安装后，AI agent 可以用它生成项目说明、任务列表和验证规则，也可以在后台持续执行任务。运行过程中，NodeKit 会记录日志和证据；任务中断后，可以用恢复命令接着跑。涉及删除文件、提交 Slurm / COMSOL / DFT 任务这类高风险操作时，它会先停下来检查。

当前版本已经可用。建议先用一个小项目跑通流程，再交给昂贵计算或大批量任务。

### 它适合什么任务

- 科研 notebook、Matlantis、ASE 工作流；
- VASP、DFT、SevenNet 数据生成和 fine-tuning；
- AI 可控的有限元计算，例如 COMSOL 参数扫描、仿真批处理和结果整理；
- RAGFlow + 本地 LLM 知识库；
- 批量论文图、数据处理、代码修复；
- 需要长时间运行、断点续跑、保留证据的多阶段项目。

### 给 AI agent 的启动指令

如果你把这个包交给 Codex、Claude Code、Cursor 或其他 AI agent，可以直接给它下面这段。指令要按字面执行，不要让 agent 自己绕过 NodeKit 的任务图、gate 或 verifier：

```text
你现在负责运行 Autopilot NodeKit。必须按这个包里的流程管理项目，不要自己另起一套计划，也不要跳过 NodeKit 生成的任务图、gate、verifier 或恢复步骤。

1. 解压 autopilot-nodekit-v0.9.1-open-source-github.zip，进入解压后包含 pyproject.toml 的目录。

2. 用 Python 3.10+ 安装工具包：

python -m pip install -e ".[dev]"

3. 进入我要自动化的项目 workspace。创建或检查 PROJECT_PROMPT.md，里面必须写清目标、输入数据、输出要求、限制条件，以及哪些步骤需要先问用户。

4. 启动 NodeKit：

python -m autopilot_nodekit smart-start --workspace . --prompt-file PROJECT_PROMPT.md --force-codex-native

5. 如果生成 START_QUESTIONS.md，必须先让用户回答。把答案写进 START_ANSWERS.yml，设置 confirmed: true，然后重新运行 smart-start。

6. 之后所有行动都以 NodeKit 的下一步命令为准：

python -m autopilot_nodekit next-command --workspace .

7. 每完成一步，都要按 NodeKit 要求留下输出和证据。不要只在聊天里说完成。

8. 遇到 startup gate、资源 gate、权限不清楚、昂贵计算、删除文件、Slurm / COMSOL / DFT 提交、外部服务调用或 final audit，必须先停下来问用户。

9. 如果窗口关闭、token 用完、worker 中断或任务卡住，不要从头重做。先运行 status、next-command 或 recover-stale，按 NodeKit 的恢复逻辑继续。
```

### 让 agent 后台连续运行

普通用户不需要自己盯终端。如果你希望任务持续推进，把这段发给 agent：

```text
请按 NodeKit 后台模式运行这个项目。

先检查后台能力。通过后启动一个 worker，worker-id 用 codex-worker，max-cycles 设为 0。

max-cycles 0 表示不限制 NodeKit 的循环次数。只要没有遇到 gate、错误或外部限制，就一轮接一轮继续迭代。

启动后不要每轮都问我。只在遇到 gate、错误、昂贵计算、权限问题或最终验收时汇报并等待确认。
```

agent 需要用到的核心命令只有这两条：

```bash
python -m autopilot_nodekit background-doctor --workspace .
python -m autopilot_nodekit launch-background --workspace . --worker-id codex-worker --max-cycles 0
```

### 什么时候会停下来问你

后台正常运行时，agent 不应该每个小任务都来问你。它只应该在需要你拍板的地方停下来，比如：

- 项目刚开始时，目标、数据路径、输出格式或限制条件还没说清；
- 文件路径、系统权限、账号权限或外部服务权限不明确；
- 你选择了 `balanced` 或 `strict`，需要先看第一个小样，再决定是否批量继续；
- 同一个问题连续修复失败，需要你判断方向是不是错了；
- 要提交昂贵计算或会影响外部系统的任务，比如 Slurm、COMSOL、DFT、云服务调用；
- 最后验收时，需要你确认结果是否真的可交付。

如果你希望它少问一些，可以在一开始就把权限说清楚。例如把这段写进 `PROJECT_PROMPT.md`：

```text
本项目中，你可以自动执行低风险步骤，包括读取项目文件、整理本地文件、运行测试、生成中间结果、按 NodeKit 任务图继续推进。

遇到以下情况必须先问我：删除或覆盖大量文件、提交昂贵计算、调用外部付费服务、使用凭据、改变远端仓库、处理隐私数据、最终验收。
其他普通步骤不要反复询问，按 NodeKit 的任务图、gate 和 verifier 继续运行。
```

### 中断后告诉 AI agent 什么

如果 Codex 窗口关了、token 用完了、worker 挂了，用户不需要自己敲恢复命令。重新打开 AI agent 后，把这段话发给它：

```text
请恢复这个 Autopilot NodeKit 项目，不要从头开始。

先读取当前 workspace 里的 NodeKit 状态，检查后台 worker、项目状态和下一步任务。按 NodeKit 的 status、background-status 和 next-command 逻辑判断当前应该继续哪里。

如果发现某个 run 长时间停在 running 状态，先按 NodeKit 的 recover-stale 逻辑判断它是不是已经卡住；确认 stale 后，再把它标记为失败，让 repair 流程接手。

如果某个 repair 任务已经通过，但原来的父任务还没有释放，按 NodeKit 的 resolve-by-repair 逻辑处理。

恢复过程中不要删除运行记录，不要跳过 gate，不要自己重新规划整个项目。处理完后告诉我：当前卡在哪一步、你做了什么恢复动作、下一步准备做什么。
```

### 三个模式怎么选

```text
fast      停得少，适合需求非常明确的任务。
balanced  推荐默认；先做一个 pilot，人看一次，再批量 loop。
strict    停得多，适合高风险或第一次跑的项目。
```

### Shell 安全加固

NodeKit 在执行 verifier 和启动检查时会自动做 shell 安全检查。普通用户不用额外手动检查。

需要记住的规则很简单：

- verifier 只做只读检查，例如确认文件是否存在、测试是否通过、结果是否生成；
- `sbatch`、`srun`、`scancel`、`qsub`、`rm -rf` 这类会改变系统状态的命令，不应该藏在 verifier 里；
- Slurm、COMSOL、DFT、云服务调用和删除文件这类动作，应该作为明确任务执行，并经过人工或资源 gate。

如果你让 agent 写自己的 verifier，也把这条规则写进 `PROJECT_PROMPT.md`：verifier 只能检查结果，不能提交任务、取消任务或删除数据。

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

如果你使用云端 AI agent，或任何会把上下文发到外部服务的模型，建议不要把真实运行数据和私密信息交给模型，也不要提交到仓库。例如：

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

如果你修改了这个包，或者准备重新发布到 GitHub，建议先做本地验证。下面这些命令要在 NodeKit 包根目录运行，也就是解压后包含 `pyproject.toml`、`autopilot_nodekit/` 和 `tests/` 的文件夹，不是在你要自动化的业务项目里运行。

```bash
python -m pip install -e ".[dev]"
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

This package is ready to publish as a GitHub project. After installation, an AI agent can use it to create the project spec, task list, and verification rules, then keep working in the background. NodeKit records logs and evidence as it runs, can recover interrupted work, and checks risky actions before they run.

Status: usable. Start with a small project to learn the flow before using it for expensive compute or large batches.

### Good fit

- Research notebooks, Matlantis, and ASE workflows.
- VASP, DFT, SevenNet data generation, and fine-tuning pipelines.
- AI-controllable finite-element workflows, such as COMSOL parameter sweeps, simulation batches, and result collection.
- RAGFlow + local LLM knowledge bases.
- Batch figure generation, data processing, and code repair.
- Long-running staged projects that need recovery and evidence.

### Instruction for the AI agent

If you give this package to Codex, Claude Code, Cursor, or another AI agent, paste the instruction below. It should be followed literally; the agent should not bypass NodeKit's task graph, gates, verifiers, or recovery flow:

```text
You are responsible for running Autopilot NodeKit. You must manage the project through the workflow included in this package. Do not create a separate plan, and do not skip the task graph, gates, verifiers, or recovery steps generated by NodeKit.

1. Unzip autopilot-nodekit-v0.9.1-open-source-github.zip, then enter the extracted folder that contains pyproject.toml.

2. Install the toolkit with Python 3.10+:

python -m pip install -e ".[dev]"

3. Go to the project workspace that should be automated. Create or inspect PROJECT_PROMPT.md. It must state the goal, input data, output requirements, constraints, and any steps that should ask the user first.

4. Start NodeKit:

python -m autopilot_nodekit smart-start --workspace . --prompt-file PROJECT_PROMPT.md --force-codex-native

5. If START_QUESTIONS.md is created, ask the user for answers first. Write them into START_ANSWERS.yml, set confirmed: true, and rerun smart-start.

6. After that, all work must follow NodeKit's next command:

python -m autopilot_nodekit next-command --workspace .

7. For every completed step, write the outputs and evidence requested by NodeKit. Do not only say that the work is done in chat.

8. Stop and ask the user before startup gates, resource gates, unclear permissions, expensive compute, file deletion, Slurm / COMSOL / DFT submission, external service calls, or final audit.

9. If the window closes, tokens run out, a worker stops, or a task gets stuck, do not restart from scratch. Run status, next-command, or recover-stale first, then continue through NodeKit's recovery flow.
```

### Tell the agent to keep running in the background

Users do not need to watch the terminal. If you want the project to keep moving, paste this to the agent:

```text
Run this project in NodeKit background mode.

First check whether the background backend is available. If it passes, start one worker with worker-id codex-worker and max-cycles set to 0.

max-cycles 0 means NodeKit does not set a cycle limit. It will keep iterating until it hits a gate, an error, or an external limit.

After starting, do not ask me after every cycle. Report and wait only when you hit a gate, an error, expensive compute, a permission issue, or final audit.
```

The agent only needs these core commands:

```bash
python -m autopilot_nodekit background-doctor --workspace .
python -m autopilot_nodekit launch-background --workspace . --worker-id codex-worker --max-cycles 0
```

### When the agent should ask you

During a normal background run, the agent should not ask you about every small task. It should stop only when your judgment is needed, for example:

- the project goal, data path, output format, or constraints are still unclear;
- file paths, system permissions, account permissions, or external-service access are unclear;
- you chose `balanced` or `strict`, and the first small pilot needs review before batching;
- the same issue keeps failing after repair attempts;
- the task will spend real compute or affect an external system, such as Slurm, COMSOL, DFT, or cloud service calls;
- the project is at final audit and needs delivery approval.

If you want fewer interruptions, state the permission rules at the start. For example, add this to `PROJECT_PROMPT.md`:

```text
For this project, you may automatically perform low-risk steps, including reading project files, organizing local files, running tests, generating intermediate outputs, and continuing through the NodeKit task graph.

You must ask me before deleting or overwriting many files, submitting expensive compute, calling paid external services, using credentials, changing a remote repository, handling private data, or approving final delivery.
For normal low-risk steps, do not ask repeatedly. Continue through NodeKit's task graph, gates, and verifiers.
```

### What to tell the agent after interruption

If the Codex window closes, tokens run out, or a worker stops, the user does not need to run recovery commands manually. Reopen the AI agent and paste this:

```text
Please recover this Autopilot NodeKit project. Do not start over.

First read the current NodeKit state in this workspace. Check the background worker, project status, and next task. Use NodeKit's status, background-status, and next-command logic to decide where to continue.

If a run has stayed in running state for too long, use NodeKit's recover-stale logic to decide whether it is stuck. After confirming it is stale, mark it failed so the repair flow can take over.

If a repair task has passed but the original parent task is still blocked, handle it through NodeKit's resolve-by-repair logic.

During recovery, do not delete run records, do not skip gates, and do not re-plan the whole project yourself. When done, tell me where the project was stuck, what recovery action you took, and what you will do next.
```

### Gate modes

```text
fast      Fewer stops, best for well-scoped work.
balanced  Recommended default; run one pilot, review it, then batch.
strict    More checkpoints, best for high-risk or first-time projects.
```

### Shell-safety hardening

NodeKit automatically runs shell-safety checks for verifiers and startup checks. Most users do not need to run a separate precheck command.

The rule is simple:

- verifiers should only perform read-only checks, such as confirming files exist, tests pass, or outputs were created;
- commands that mutate system state, such as `sbatch`, `srun`, `scancel`, `qsub`, and `rm -rf`, should not be hidden inside verifiers;
- Slurm, COMSOL, DFT, cloud-service calls, and file deletion should run as explicit tasks with a human or resource gate.

If you ask an agent to write custom verifiers, put this rule in `PROJECT_PROMPT.md`: verifiers may check results, but they may not submit jobs, cancel jobs, or delete data.

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

When using a cloud AI agent, or any setup that sends context to an external service, avoid giving it real runtime data or private information. Do not commit that material to the repository either:

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

If you modify this package or prepare a new GitHub release, run local verification first. Run these commands in the NodeKit package root, the extracted folder that contains `pyproject.toml`, `autopilot_nodekit/`, and `tests/`. Do not run them inside the separate project workspace you want to automate.

```bash
python -m pip install -e ".[dev]"
python -m compileall -q autopilot_nodekit tests
python -m pytest -q
```

More documentation:

- `docs/GITHUB_PUBLISHING.md`
- `docs/PUBLIC_QUICKSTART.zh-CN.md`
- `docs/V09_BOOTSTRAP_HARDENING.md`
