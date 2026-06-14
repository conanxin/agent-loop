# agent-loop 中文指南

OpenClaw ↔️ Hermes 双 Agent 文件中继循环协议。

## 项目介绍

agent-loop 是一个**基于文件系统**的双 Agent 协作协议：

- **OpenClaw** 负责规划、生成命令、评审报告
- **Hermes** 负责执行命令、生成报告
- **Telegram** 只承载两行状态通知（非结构化数据）

## 为什么不用 Telegram 承载完整结构化报告

| 问题 | 文件系统方案 |
|---|---|
| Token 限制 | 无限制 |
| 格式漂移 | 严格的 BEGIN/END 标记 |
| 无法版本控制 | Git 管理 |
| 无法 diff | 文本文件可 diff |
| 无法 grep | 标准文本可搜索 |

Telegram 只发送：
```
HERMES_STATUS: REPORT_WRITTEN
HERMES_REPORT_PATH: ~/.agent-loop/goals/my-project/hermes-reports/001.md
```

## 架构图

```
┌─────────────┐      ┌─────────────┐      ┌─────────────┐
│   OpenClaw  │◄────►│  文件系统   │◄────►│   Hermes    │
│  (规划/评审) │      │  (中继)     │      │  (执行)     │
└─────────────┘      └─────────────┘      └─────────────┘
       │                     │                    │
       │              ┌──────┴──────┐            │
       │              │   Telegram  │            │
       │              │  (2行通知)  │            │
       │              └─────────────┘            │
       │                                         │
       ▼                                         ▼
openclaw-decisions/                      hermes-commands/
hermes-reports/                          hermes-reports/
```

## 5 分钟快速安装

### 一键安装

```bash
git clone https://github.com/conanxin/agent-loop.git
cd agent-loop
./scripts/install-all.sh
export PATH="$HOME/.agent-loop/bin:$PATH"
```

### 分步安装

```bash
# 仅安装工具
./scripts/install.sh

# 仅安装 Skills
./scripts/install-skills.sh

# 完整安装（工具 + Skills + 冒烟测试）
./scripts/install-all.sh
```

## 安装 OpenClaw / Hermes Skills

```bash
./scripts/install-skills.sh
```

验证安装：
```bash
# OpenClaw Skill
cat ${OPENCLAW_SKILLS_DIR:-$HOME/.openclaw/workspace/skills}/hermes-agent-loop/SKILL.md

# Hermes Skill
cat ${HERMES_SKILLS_DIR:-$HOME/.hermes/skills}/openclaw-command-executor/SKILL.md
```

## 手动 Relay 完整流程

### 1. 初始化 Goal

```bash
agent-loop-init-goal my-project "实现功能 X"
```

### 2. 设置状态

```bash
agent-loop-set-state my-project COMMAND_READY
```

### 3. 写入命令文件

创建 `~/.agent-loop/goals/my-project/hermes-commands/001.md`：

```markdown
BEGIN_HERMES_COMMAND
goal_id: my-project
iteration: 1
command_type: implement
objective: 实现功能 X
instructions:
  1. 运行测试
  2. 实现功能
  3. 用 make validate 验证
validation: 测试通过，make validate 返回 0
report_back: HERMES_STATUS: REPORT_WRITTEN
stop_conditions: 如果测试失败，报告 FAIL
END_HERMES_COMMAND
```

### 4. 打印命令

```bash
agent-loop-relay --once my-project
```

复制打印的命令给 Hermes。

### 5. 标记已派发

```bash
agent-loop-relay --once my-project --mark-dispatched
```

### 6. 记录报告

Hermes 执行后写入报告：

```bash
agent-loop-relay --once my-project --report-path ~/.agent-loop/goals/my-project/hermes-reports/001.md
```

### 7. 生成评审提示

```bash
agent-loop-relay --judge-prompt my-project
```

复制提示给 OpenClaw。

### 8. 标记评审中

```bash
agent-loop-relay --judge-prompt my-project --mark-judging
```

### 9. 摄入决策

OpenClaw 写入决策后：

```bash
agent-loop-relay --decision-path my-project ~/.agent-loop/goals/my-project/openclaw-decisions/001.md
```

### 10. 验证最终状态

```bash
agent-loop-show my-project
```

## 命令参考

| 命令 | 说明 |
|---|---|
| `agent-loop-init-goal <id> "描述"` | 创建新 goal |
| `agent-loop-set-state <id> <状态>` | 手动设置状态 |
| `agent-loop-show <id>` | 显示 goal 状态 |
| `agent-loop-relay --once <id>` | 打印命令（不推进） |
| `agent-loop-relay --once <id> --mark-dispatched` | 推进到 DISPATCHED_TO_HERMES |
| `agent-loop-relay --once <id> --report-path <路径>` | 记录报告，推进到 HERMES_REPORT_WRITTEN |
| `agent-loop-relay --judge-prompt <id>` | 生成评审提示 |
| `agent-loop-relay --judge-prompt <id> --mark-judging` | 推进到 OPENCLAW_JUDGING |
| `agent-loop-relay --decision-path <id> <文件>` | 摄入决策，推进到最终状态 |

## 状态机

```
INIT → COMMAND_READY → DISPATCHED_TO_HERMES → HERMES_REPORT_WRITTEN → OPENCLAW_JUDGING → DONE
```

完整状态图见 [docs/STATE_MACHINE.md](docs/STATE_MACHINE.md)。

## BEGIN_HERMES_REPORT Schema

```yaml
BEGIN_HERMES_REPORT
goal_id: <字符串>
iteration: <整数>
status: PASS | PARTIAL | FAIL | BLOCKED
summary: <单行摘要>
changed_files: <文件列表或 "none">
commands_run: <命令列表>
validation_result: <结构化验证结果>
commit: <Git SHA 或 "none">
report_path: <绝对路径>
issues: <问题列表或 "none">
recommendation: <下一步建议>
END_HERMES_REPORT
```

## BEGIN_OPENCLAW_DECISION Schema

```yaml
BEGIN_OPENCLAW_DECISION
goal_id: <字符串>
iteration: <整数>
decision: DONE | NEXT_COMMAND | REPAIR_COMMAND | PARTIAL | BLOCKED | NEEDS_HUMAN_REVIEW
requires_human_approval: true | false
reason: <说明>
next_expected_result: <预期结果>
END_OPENCLAW_DECISION
```

## 常见问题

### 工具未找到

```bash
export PATH="$HOME/.agent-loop/bin:$PATH"
source ~/.bashrc
```

### 状态不匹配

```bash
agent-loop-show <goal_id>
agent-loop-set-state <goal_id> <正确状态>
```

### 决策文件缺少字段

确保包含所有 6 个必填字段：`goal_id`, `iteration`, `decision`, `requires_human_approval`, `reason`, `next_expected_result`。

## 安全边界

- **不自动执行**：relay 打印命令，人工确认
- **不修改真实项目**：验证任务使用 `make validate`（只读）
- **不泄露令牌**：密钥存放在 `.env`（gitignored）
- **不泄露路径**：文档中使用 `~/.agent-loop` 而非绝对路径

完整安全规则见 [docs/SAFETY_BOUNDARIES.md](docs/SAFETY_BOUNDARIES.md)。

## 英文文档

[README.md](README.md) — 英文版完整文档
