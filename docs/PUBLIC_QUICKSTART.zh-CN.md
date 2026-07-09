# 公开版快速示例

一句话触发：

```text
基于 autopilot-nodekit 包里的逻辑，完成以下任务：为一个科研项目建立可验证、可恢复、可审计的自动化 loop。
```

典型流程：

```bash
python -m autopilot_nodekit smart-start --workspace . --prompt-file PROJECT_PROMPT.md --force-codex-native
python -m autopilot_nodekit next-command --workspace .
python -m autopilot_nodekit background-doctor --workspace .
python -m autopilot_nodekit launch-background --workspace . --worker-id codex-worker --max-cycles 0
python -m autopilot_nodekit background-status --workspace . --worker-id codex-worker
```

遇到中断：

```bash
python -m autopilot_nodekit status --workspace .
python -m autopilot_nodekit next-command --workspace .
python -m autopilot_nodekit recover-stale --workspace . --run-id <RUN_ID> --mark-failed
```

如果 repair 通过但父任务仍卡住：

```bash
python -m autopilot_nodekit resolve-by-repair --workspace . --failed-task-id <FAILED_TASK> --repair-task-id <PASSED_REPAIR_TASK>
```
