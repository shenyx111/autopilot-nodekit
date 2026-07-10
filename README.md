# Autopilot NodeKit v0.9.3

[中文](#中文) | [日本語](#日本語) | [English](#english)

## 中文

Autopilot NodeKit 是一个开源的 loop engineering 工具包，用来让 Codex、Claude Code、Cursor 等 AI agent 更方便、更安全地处理长任务。它会把任务拆成可恢复、可验证、可审计的任务图；后台 worker 负责执行，operator 负责处理普通 repair / recover / resolve，用户只在真正需要判断时介入。

它的目标很简单：不要让用户变成 next-command 按钮。

适合：

- 科研 notebook、Matlantis、ASE 工作流；
- VASP、DFT、SevenNet 数据生成和 fine-tuning；
- AI 可控的有限元计算，例如 COMSOL 参数扫描、仿真批处理和结果整理；
- RAGFlow + 本地 LLM 知识库；
- 批量数据处理、论文图生成、长期代码修复；
- 需要长时间运行、断点续跑、保留证据的多阶段项目。

### v0.9.3 重点

v0.9.3 主要改了三件事：

1. `worker-loop` 默认带 operator/supervisor。后台 worker 没有 ready task 时，operator 会自动处理普通控制面动作。
2. repair / recover / resolve 不再主要靠用户提醒。普通 failed task、passed repair、stale run 和下游释放会自动推进。
3. 加入 mainline-first scheduling guard。历史 failed repair 如果已经不再阻塞当前主线，就只作为历史证据保留，不会抢走主线任务。

默认行为：

```text
ready task -> 后台 worker 自动执行
failed task -> operator 自动 add-repair-task
passed repair -> operator 自动 resolve-by-repair
stale run -> operator 自动 recover-stale
mainline released -> 自动继续 claim 下一个 ready task
```

NodeKit 仍然不会自动批准 human gate，也不会自动执行危险操作、昂贵计算、删除文件、使用凭据或修改远端仓库。

### 发给 AI agent 的启动指令

在 Codex、Claude Code、Cursor 或其他 AI agent 的聊天输入框里粘贴下面整段。你只需要改尖括号里的内容，不要把这段拆开，也不要自己逐条敲命令。

```text
你现在负责运行 Autopilot NodeKit。必须按这个包里的流程管理项目，不要另起一套计划，也不要跳过任务图、gate、verifier、repair、operator 或恢复步骤。

我的任务：
<写清楚你要做什么、输入文件在哪里、希望输出什么、最终结果放到哪里、限制是什么。>

运行方式：
<写“先前台跑通流程”或“后台连续运行”。如果是后台连续运行，请你自动运行 NodeKit 的后台检查和后台 worker 启动命令。用户不需要手动执行这些命令。worker-id 用 codex-worker，max-cycles 设为 0。>

后台 Codex 模型与设置：
<填写希望后台 worker 使用的模型和其他 Codex 设置，例如“model 使用 MODEL_NAME”。启动 worker 前，先确认当前 Codex CLI 支持这些设置。每次启动后台 Codex 时都要用 codex exec --model 指定模型，其他设置用受支持的 --config key=value 传入。留空就使用本机现有的 Codex 设置。>

最终输出位置：
<例如 outputs/final/。完成后必须告诉我每个主要结果文件的具体路径。>

权限规则：
<写清楚可以自动做什么，哪些必须先问我。比如：可以自动读取项目文件、整理本地文件、运行测试和生成中间结果；删除或覆盖大量文件、提交昂贵计算、调用外部付费服务、使用凭据、改变远端仓库、处理隐私数据、最终验收前必须先问我。>

请先解压并安装 Autopilot NodeKit，然后进入目标 workspace，根据上面的任务信息创建或检查 PROJECT_PROMPT.md，并运行 smart-start。

如果信息缺失，先生成 START_QUESTIONS.md 问我。确认后继续。

之后由 NodeKit 的后台 worker 和 operator 自动推进。普通 repair、resolve-by-repair、recover-stale、status、validate、background-status 不需要每次问我。

只有遇到 human gate、危险操作、昂贵计算、连续失败、worker 无法恢复或 final audit，才停下来通知我。

完成后必须告诉我最终结果放在哪里，优先给出明确路径。
```

### Agent 需要的核心命令

普通用户通常不需要自己运行这些命令。它们放在这里，是给 agent 或开发者确认流程用的。

安装：

```bash
python -m pip install -e ".[dev]"
```

启动项目：

```bash
python -m autopilot_nodekit smart-start --workspace . --prompt-file PROJECT_PROMPT.md --force-codex-native
```

后台连续运行：

```bash
python -m autopilot_nodekit background-doctor --workspace .
python -m autopilot_nodekit launch-background --workspace . --worker-id codex-worker --max-cycles 0
```

`--max-cycles 0` 表示不限制 NodeKit 的循环次数。只要没有遇到 gate、错误或外部限制，它会一轮接一轮继续迭代。

### 什么时候会问你

正常后台运行时，agent 不应该每个小任务都问你。它只应该在这些情况停下来：

- startup gate、pilot gate、final audit；
- 路径、权限、账号、凭据不清楚；
- 要删除或覆盖大量文件；
- 要提交、取消或修改昂贵计算，例如 Slurm、DFT、COMSOL、云服务；
- 同一问题连续 repair 超过安全深度；
- worker 无法自动恢复；
- verifier 或 Santa 发现严重风险。

普通 task passed、普通 repair、普通 resolve-by-repair、普通 recover-stale 不应该打扰用户。

### 中断后告诉 AI agent 什么

如果窗口关闭、token 用完、worker 退出，用户不需要自己敲恢复命令。重新打开 agent 后，把这段话发给它：

```text
请恢复这个 Autopilot NodeKit 项目，不要从头开始。

先读取当前 workspace 里的 NodeKit 状态，检查后台 worker、项目状态和下一步任务。按 NodeKit 的 status、background-status、next-command 和 operator 逻辑判断当前应该继续哪里。

如果发现 run 长时间停在 running 状态，按 NodeKit 的 recover-stale 逻辑处理。

如果 repair 已经通过但父任务仍 failed，按 NodeKit 的 resolve-by-repair 逻辑处理。

恢复过程中不要删除运行记录，不要跳过 gate，不要重新规划整个项目。处理完后告诉我：当前卡在哪一步、你做了什么恢复动作、下一步准备做什么。
```

### 结果会放在哪里

最终结果的位置由你的任务决定。建议在启动指令的“最终输出位置”里直接指定，例如：

```text
最终结果请放在 outputs/final/，完成后告诉我每个主要文件的路径。
```

如果你没有指定，agent 应该在开始时先问你，或者使用项目里的 `outputs/`、`results/`、`reports/` 这类目录。`runs/` 是 NodeKit 的过程记录和证据，不一定是最终交付结果。

### Shell 安全

verifier 只能做只读检查，例如检查文件是否存在、测试是否通过、结果是否生成。不要把这些命令藏进 verifier：

```text
sbatch / srun / scancel / qsub / qdel / rm -rf / 反引号命令替换 / $(...)
```

NodeKit 会对 verifier 和启动检查做 shell-safety lint，降低误触发危险命令的概率。Slurm、COMSOL、DFT、云服务调用和删除文件，应该作为明确任务执行，并经过人工或资源 gate。

### 不要提交到 GitHub 的内容

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

如果你修改了这个包，或者准备重新发布到 GitHub，建议先做本地验证。下面这些命令要在 NodeKit 包根目录运行，也就是包含 `pyproject.toml`、`autopilot_nodekit/` 和 `tests/` 的文件夹。

```bash
python -m pip install -e ".[dev]"
python -m compileall -q autopilot_nodekit tests
python -m pytest -q
```

## 日本語

Autopilot NodeKit は、Codex、Claude Code、Cursor などの AI agent が長いタスクを扱いやすくするための、オープンソースの loop engineering ツールキットです。作業を復旧可能、検証可能、監査可能なタスクグラフに分けます。バックグラウンド worker が実行を担当し、operator が通常の repair / recover / resolve を処理します。ユーザーは判断が必要な場面だけ介入します。

目標はシンプルです。ユーザーを next-command ボタンにしないことです。

向いている用途：

- 研究 notebook、Matlantis、ASE ワークフロー；
- VASP、DFT、SevenNet のデータ生成や fine-tuning；
- COMSOL のパラメータスイープ、シミュレーション一括実行、結果整理など、AI が制御できる有限要素計算；
- RAGFlow + ローカル LLM の知識ベース；
- バッチデータ処理、論文図の生成、長いコード修正；
- 長時間実行、途中再開、証拠保存が必要な多段階プロジェクト。

### v0.9.3 の要点

v0.9.3 の主な変更は三つです。

1. `worker-loop` はデフォルトで operator/supervisor を含みます。バックグラウンド worker に ready task がない場合、operator が通常の制御面処理を行えます。
2. repair、recovery、repair resolution は、ユーザーの手動リマインドに頼らない形になりました。通常の failed task、passed repair、stale run、下流タスクの解放は自動で進みます。
3. mainline-first scheduling guard を追加しました。現在の主線をもうブロックしていない過去の failed repair は証拠として残りますが、主線の ready task より優先されません。

デフォルトの動き：

```text
ready task -> バックグラウンド worker が実行
failed task -> operator が repair task を追加
passed repair -> operator が resolve-by-repair を実行
stale run -> operator が recover-stale を実行
mainline released -> 次の ready task を自動で claim
```

NodeKit は human gate、危険な操作、高価な計算、ファイル削除、認証情報の使用、リモートリポジトリ変更を自動承認しません。

### AI agent に渡す起動指示

下のブロック全体を Codex、Claude Code、Cursor などの AI agent のチャット入力欄に貼り付けてください。山括弧の中だけを書き換えます。ブロックを分けたり、コマンドを自分で一つずつターミナルに入力したりする必要はありません。

```text
あなたは Autopilot NodeKit を使ってこのプロジェクトを進めます。このパッケージに含まれる手順に従って管理してください。別の計画を勝手に作らず、タスクグラフ、gate、verifier、repair flow、operator、recovery steps を飛ばさないでください。

私のタスク：
<やりたいこと、入力ファイルの場所、期待する出力、最終結果を保存する場所、制約を書いてください。>

実行方式：
<「まず前面で流れを確認する」または「バックグラウンドで継続実行する」と書いてください。バックグラウンド実行の場合は、NodeKit の background check と background worker の起動をあなたが実行してください。ユーザーはこれらのコマンドを手動実行しません。worker-id は codex-worker、max-cycles は 0 にしてください。>

バックグラウンド Codex のモデルと設定：
<バックグラウンド worker で使うモデルとその他の Codex 設定を記入してください。例：「model は MODEL_NAME」。worker を起動する前に、現在の Codex CLI がその設定をサポートしていることを確認してください。バックグラウンド Codex を起動するたびに codex exec --model でモデルを指定し、その他の設定はサポートされている --config key=value で渡してください。空欄の場合は、ローカルにある現在の Codex 設定を使ってください。>

最終出力の保存先：
<例：outputs/final/。完了後、主要な結果ファイルの正確なパスを教えてください。>

権限ルール：
<自動で実行してよいこと、先に確認が必要なことを書いてください。例：プロジェクトファイルの読み取り、ローカルファイル整理、テスト実行、中間結果生成は自動でよい；大量の削除や上書き、高価な計算、外部有料サービス、認証情報、リモートリポジトリ変更、個人情報や非公開データ、最終納品の承認は先に確認してください。>

まず Autopilot NodeKit を解凍してインストールしてください。次に対象 workspace に入り、上のタスク情報から PROJECT_PROMPT.md を作成または確認し、smart-start を実行してください。

情報が不足している場合は START_QUESTIONS.md を作成して、先に私に質問してください。確認後に続けてください。

その後は NodeKit の background worker と operator に進行を任せてください。通常の repair、resolve-by-repair、recover-stale、status、validate、background-status では毎回私に聞かないでください。

human gate、危険な操作、高価な計算、連続失敗、復旧できない worker 問題、final audit のときだけ止まって通知してください。

完了したら、最終結果がどこにあるかを正確なパスで教えてください。
```

### Agent が使う主なコマンド

通常のユーザーがこれらを手動で実行する必要はほとんどありません。agent や開発者が流れを確認できるように載せています。

インストール：

```bash
python -m pip install -e ".[dev]"
```

プロジェクト開始：

```bash
python -m autopilot_nodekit smart-start --workspace . --prompt-file PROJECT_PROMPT.md --force-codex-native
```

バックグラウンドで継続実行：

```bash
python -m autopilot_nodekit background-doctor --workspace .
python -m autopilot_nodekit launch-background --workspace . --worker-id codex-worker --max-cycles 0
```

`--max-cycles 0` は NodeKit 側でサイクル数の上限を設けないという意味です。gate、エラー、外部制限に当たるまで反復します。

### Agent がユーザーに確認すべき場面

通常のバックグラウンド実行では、agent が小さなタスクごとに質問する必要はありません。質問すべき場面は主に次の通りです。

- startup gate、pilot gate、final audit；
- パス、権限、アカウント、認証情報が不明な場合；
- 多数のファイルを削除または上書きする場合；
- Slurm、DFT、COMSOL、クラウドサービスなど、高価な計算や外部システムを動かす場合；
- 同じ問題の repair が安全深度を超えて失敗する場合；
- worker が自動復旧できない場合；
- verifier または Santa が重大なリスクを検出した場合。

通常の passed task、repair task、resolve-by-repair、recover-stale でユーザーを中断しないでください。

### 中断後に agent へ伝えること

ウィンドウが閉じた、token が尽きた、worker が終了した、といった場合でも、ユーザーが復旧コマンドを手動実行する必要はありません。agent を開き直して、次を貼り付けてください。

```text
この Autopilot NodeKit プロジェクトを復旧してください。最初からやり直さないでください。

まず現在の workspace にある NodeKit の状態を読み取ってください。background worker、プロジェクト状態、次のタスクを確認してください。NodeKit の status、background-status、next-command、operator logic を使って、どこから続けるべきか判断してください。

run が長時間 running のままなら、NodeKit の recover-stale logic で処理してください。

repair task が passed なのに親 task が failed のままなら、NodeKit の resolve-by-repair logic で処理してください。

復旧中に run records を削除しないでください。gate を飛ばさないでください。プロジェクト全体を再計画しないでください。完了後、どこで止まっていたか、どんな復旧処理をしたか、次に何をするかを教えてください。
```

### 結果の保存場所

最終結果の場所はタスクによって変わります。起動指示の「最終出力の保存先」で指定するのがおすすめです。

```text
最終結果は outputs/final/ に保存し、完了後に主要ファイルのパスを教えてください。
```

指定がない場合、agent は開始時に確認するか、`outputs/`、`results/`、`reports/` のようなプロジェクト内ディレクトリを使うべきです。`runs/` は NodeKit の証拠とタスク記録であり、最終納品物そのものとは限りません。

### Shell safety

verifier はファイルの存在、テスト通過、出力生成などの読み取り専用チェックだけを行うべきです。次のようなコマンドを verifier に隠さないでください。

```text
sbatch / srun / scancel / qsub / qdel / rm -rf / backtick command substitution / $(...)
```

NodeKit は verifier と startup checks に shell-safety lint をかけます。Slurm、COMSOL、DFT、クラウドサービス呼び出し、ファイル削除は明示的な task として実行し、human gate または resource gate を通してください。

### GitHub に公開しないもの

クラウド AI agent や、外部サービスに文脈を送るモデルを使う場合、実際の実行データや非公開情報を渡さないことをおすすめします。リポジトリにもコミットしないでください。

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

### ローカル検証

このパッケージを変更した場合や GitHub に公開する前には、NodeKit パッケージのルートで検証してください。つまり `pyproject.toml`、`autopilot_nodekit/`、`tests/` があるフォルダです。

```bash
python -m pip install -e ".[dev]"
python -m compileall -q autopilot_nodekit tests
python -m pytest -q
```

## English

Autopilot NodeKit is an open-source loop-engineering toolkit for Codex, Claude Code, Cursor, and similar AI agents. It turns long work into a recoverable, verifiable, auditable task graph. Background workers execute tasks, while the operator handles routine repair, recovery, and repair resolution. The user steps in only when judgment is actually needed.

Main goal: do not turn the user into the next-command button.

Good fit:

- research notebooks, Matlantis, and ASE workflows;
- VASP, DFT, SevenNet data generation, and fine-tuning;
- AI-controllable finite-element workflows, such as COMSOL parameter sweeps and simulation batches;
- RAGFlow + local LLM knowledge bases;
- batch data processing, paper figures, and long-running code repair;
- staged projects that need recovery, evidence, and final audit.

### What is new in v0.9.3

v0.9.3 changes three practical areas:

1. `worker-loop` includes operator/supervisor behavior by default. When a background worker has no ready task, the operator can handle routine control-plane work.
2. repair, recovery, and repair resolution no longer depend mainly on user reminders. Routine failed tasks, passed repairs, stale runs, and downstream release are handled automatically.
3. The scheduler includes a mainline-first guard. Historical failed repair branches that no longer block the active frontier remain as evidence, but they do not steal scheduling priority from mainline-ready work.

Default behavior:

```text
ready task -> background worker executes it
failed task -> operator adds a repair task
passed repair -> operator runs resolve-by-repair
stale run -> operator runs recover-stale
mainline released -> loop claims the next ready task
```

NodeKit still does not approve human gates, dangerous operations, expensive compute, file deletion, credential use, or remote-repository changes.

### Instruction for the AI agent

Paste the full block below into the chat input of Codex, Claude Code, Cursor, or another AI agent. Replace only the angle-bracket sections. Do not split the prompt, and do not manually type each command into a terminal yourself.

```text
You are responsible for running Autopilot NodeKit. You must manage the project through the workflow included in this package. Do not create a separate plan, and do not skip the task graph, gates, verifiers, repair flow, operator, or recovery steps.

My task:
<write what you want done, where the input files are, what output you expect, where final results should be saved, and what constraints apply.>

Run mode:
<write "run the first flow in the foreground" or "keep running in the background". If you choose background mode, run NodeKit's background check and start the background worker yourself. The user does not need to run those commands manually. Use worker-id codex-worker and max-cycles 0.>

Background Codex model and settings:
<state the model and any other Codex settings for the background worker, for example, "use MODEL_NAME as the model". Before starting the worker, confirm that the current Codex CLI supports those settings. Pass the model with codex exec --model and other supported settings with --config key=value every time background Codex starts. Leave this blank to use the current local Codex settings.>

Final output location:
<for example, outputs/final/. When finished, tell me the exact path of each main result file.>

Permission rules:
<state what may run automatically and what must ask first. For example: you may read project files, organize local files, run tests, and generate intermediate outputs; ask me before deleting or overwriting many files, submitting expensive compute, calling paid external services, using credentials, changing a remote repository, handling private data, or approving final delivery.>

First unzip and install Autopilot NodeKit. Then enter the target workspace, create or inspect PROJECT_PROMPT.md from the task information above, and run smart-start.

If information is missing, create START_QUESTIONS.md and ask me first. Continue after confirmation.

After that, let NodeKit's background worker and operator advance the project. Routine repair, resolve-by-repair, recover-stale, status, validate, and background-status should not ask me every time.

Only stop for human gates, dangerous operations, expensive compute, repeated failures, unrecoverable worker problems, or final audit.

When complete, tell me where the final results are, preferably with exact paths.
```

### Core commands for the agent

Most users do not need to run these manually. They are shown for agents and developers who need to confirm the workflow.

Install:

```bash
python -m pip install -e ".[dev]"
```

Start a project:

```bash
python -m autopilot_nodekit smart-start --workspace . --prompt-file PROJECT_PROMPT.md --force-codex-native
```

Keep running in the background:

```bash
python -m autopilot_nodekit background-doctor --workspace .
python -m autopilot_nodekit launch-background --workspace . --worker-id codex-worker --max-cycles 0
```

`--max-cycles 0` means NodeKit does not set a cycle limit. It keeps iterating until it hits a gate, an error, or an external limit.

### When the agent should ask

During a normal background run, the agent should ask only for:

- startup gates, pilot gates, or final audit;
- unclear paths, permissions, accounts, or credentials;
- deletion or overwrite of many files;
- expensive compute or external systems such as Slurm, DFT, COMSOL, or cloud services;
- repeated repair failures beyond the safety depth;
- worker failures that cannot be recovered automatically;
- serious verifier or Santa findings.

Routine passed tasks, repair tasks, resolve-by-repair, and recover-stale should not interrupt the user.

### What to tell the agent after interruption

If the window closes, tokens run out, or a worker exits, the user does not need to run recovery commands manually. Reopen the agent and paste this:

```text
Please recover this Autopilot NodeKit project. Do not start over.

First read the current NodeKit state in this workspace. Check the background worker, project status, and next task. Use NodeKit's status, background-status, next-command, and operator logic to decide where to continue.

If a run has stayed in running state for too long, use NodeKit's recover-stale logic.

If a repair task has passed but the parent task is still failed, handle it through NodeKit's resolve-by-repair logic.

During recovery, do not delete run records, do not skip gates, and do not re-plan the whole project. When done, tell me where the project was stuck, what recovery action you took, and what you will do next.
```

### Where results are saved

The final result location depends on the task. It is best to specify it in "Final output location", for example:

```text
Save final results in outputs/final/, and tell me the path of each main file when finished.
```

If no location is specified, the agent should ask at the start or use a project directory such as `outputs/`, `results/`, or `reports/`. `runs/` stores NodeKit evidence and task records, not necessarily the final deliverable.

### Shell safety

Verifiers should only perform read-only checks, such as confirming that files exist, tests pass, or outputs were created. Do not hide these commands inside verifiers:

```text
sbatch / srun / scancel / qsub / qdel / rm -rf / backtick command substitution / $(...)
```

NodeKit runs shell-safety lint for verifiers and startup checks. Slurm, COMSOL, DFT, cloud-service calls, and file deletion should run as explicit tasks with a human or resource gate.

### Do not publish

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

If you modify this package or prepare a GitHub release, run local verification from the NodeKit package root, the folder that contains `pyproject.toml`, `autopilot_nodekit/`, and `tests/`.

```bash
python -m pip install -e ".[dev]"
python -m compileall -q autopilot_nodekit tests
python -m pytest -q
```
