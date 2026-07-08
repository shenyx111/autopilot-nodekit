# Autopilot NodeKit：一个可审计的 Codex 批量任务 Loop 示例

Autopilot NodeKit 是一个面向 Codex 的本地任务控制面。它不是让 AI “随便一直跑”，而是把一个大目标先转成项目规范、目标契约、任务清单和验证规则，再让 Codex 一次处理一个明确任务。

它适合这类工作：

- 批量生成论文图、报告图、数据分析图；
- 批量整理文件、转换格式、生成脚本；
- 批量修复代码、补测试、跑验证；
- 需要中断后恢复、失败后修复、最终可追溯的任务。

## 一个例子：做 100 张期刊图

你只需要对 Codex 说类似这一句：

```text
基于 autopilot-nodekit 包里的逻辑，完成以下任务：
为一篇 Nature 风格论文制作 100 张 publication-ready figures。输入数据在 data/ 目录。每张图必须有源数据记录、绘图脚本、PDF/PNG/SVG、caption 和 QC evidence。禁止伪造数据、禁止占位图、禁止直接修改 raw data。希望尽量自动运行，缺少关键设置时先问我。
```

之后 NodeKit 会先生成项目文件，而不是直接开跑：

```text
PROJECT_PROMPT.md          # 用户需求
PROJECT_SPEC.draft.yml     # 项目规范草案
PROJECT_SPEC.md            # 人类可读项目规范
START_QUESTIONS.md         # 缺失设置时的问题
START_ANSWERS.yml.template # 用户填写的答案模板
```

如果你的 prompt 没说清楚 gate mode、任务规模、图数量、目标期刊、数据目录等关键设置，系统会先问清楚，然后才生成任务图。

## 三种审核模式

```text
fast      少量人工审核，适合需求清楚、想尽快 loop 的任务。
balanced  先做第一个完整样例并人工确认，适合大多数科研任务。
strict    先审核 setup、目标契约、任务清单和 pilot，适合高风险任务。
```

质量底座在三种模式下基本相同：任务必须经过 verifier、Santa dual review、evidence 记录和最终审计。区别主要是人工 gate 的多少。

## 三种任务规模

```text
smoke     每个产物拆成较少任务，用于快速试跑。
standard  默认平衡模式。
prod      拆得更细，适合正式批量生产。
```

例如 100 张图，在 `prod` 模式下会生成约 400 个任务，而不是只生成十几个粗任务。这样更容易恢复、审计和纠错。

## 为什么不会“假完成”

NodeKit 的核心规则是：

```text
Codex 不能自己宣布 DONE。
```

每个任务完成后必须有：

1. 输出文件或修改证据；
2. verifier 检查结果；
3. Santa dual review，两名 reviewer 都必须给出 NICE；
4. memory / evidence / log 记录；
5. 如果失败，进入 repair loop，而不是假装完成。

如果 Codex 说任务 passed，但 verifier 或 review 没通过，控制面会把任务改成 failed。

## Token 和成本监控

因为 NodeKit 会使用 Santa-method 双审核，并且失败后可能进入 repair loop，所以 token 消耗通常会高于一次性 prompt。建议在正式批量运行前先做：

```text
1. smoke 规模试跑；
2. 查看每个任务平均 token / 运行时间 / 失败次数；
3. 再切到 standard 或 prod；
4. 对超长任务增加更清晰的 done_when 和 verifier，减少无效迭代。
```

监控重点：

```text
- 每个任务平均重试次数；
- Santa review 触发次数；
- repair loop 次数；
- final audit 失败项；
- token / 时间 / 成本是否集中在少数任务类型。
```

因此，正式任务建议不要一开始就无限大规模运行，而是先用 smoke 或 balanced pilot 确认边界和质量。

## 最常用命令

先检查可用后台方式：

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

看下一步该做什么：

```bash
python -m autopilot_nodekit next-command --workspace .
```

后台 loop：

```bash
python -m autopilot_nodekit launch-background \
  --workspace . \
  --worker-id codex-worker \
  --max-cycles 0
```

`--max-cycles 0` 表示不设置 NodeKit 层面的循环次数上限。质量控制依赖 verifier、review、repair 和 final audit，而不是简单的时间限制。

## 一句话总结

Autopilot NodeKit 的目标不是让 AI 更“自由”，而是让 Codex 在明确目标、任务图、验证器、审核、记忆和日志约束下，可靠地批量完成可追踪的任务。
