---
title: Skill Design 设计文档
version: 1.0
---

# SKILL_DESIGN.zh-CN.md

## 概述

agent-loop 使用两个 skill 来规范 OpenClaw 和 Hermes 的协作行为。本文档解释这两个 skill 的设计原则、职责边界和常见错误。

## 两个 Agent 的角色

| 角色 | 职责 | 禁止行为 |
|---|---|---|
| **OpenClaw** | Planner / Judge | 不执行命令、不修改项目代码、不伪造报告 |
| **Hermes** | Executor / Reporter | 不做规划、不做评审、不扩大执行范围 |

## 两个 Skill 的职责

### OpenClaw Skill: hermes-agent-loop

**路径**: `skills/openclaw/hermes-agent-loop/SKILL.md`

**功能**:
- `plan` 模式：生成第一个 `BEGIN_HERMES_COMMAND`
- `judge` 模式：从 Telegram 文本中评审报告（不推荐，易变形）
- `judge-path` 模式：从文件中读取报告并评审（推荐，保真）
- `auto-spec` 模式：生成协议规范文档

**关键规则**:
- plan 模式只输出 **一个** 主 `BEGIN_HERMES_COMMAND`
- 有多阶段任务时，只输出下一阶段的命令
- 不输出 inspect + implement 两个可执行块
- 人类审核要点不能包含第二个可误发的 command block

### Hermes Skill: openclaw-command-executor

**路径**: `skills/hermes/openclaw-command-executor/SKILL.md`

**功能**:
- 读取 `BEGIN_HERMES_COMMAND` 并执行
- 生成严格的 `BEGIN_HERMES_REPORT`（11 字段 schema）
- 通过 Telegram 只发送两行通知

**关键规则**:
- 只执行命令中指定的指令
- 不扩大范围（例如 `make validate` 通过后不运行 `make test`）
- 指定命令通过后停止
- canonical report = 11 字段 schema，不是 Markdown 格式
- judge validation = 15 点格式检查，不是 15 个字段

## 为什么 Telegram 只承载通知

Telegram 文本传输层已被证明会破坏严格的格式：
- `BEGIN_HERMES_REPORT` 分隔符可能丢失
- `goal_id:` 键可能被合并到值中
- 多行 YAML 字段可能变形

**解决方案**:
- Hermes 将完整报告写入文件
- Telegram 只发送两行：`HERMES_STATUS: REPORT_WRITTEN` + `HERMES_REPORT_PATH: <path>`
- OpenClaw 通过 `judge-path` 读取文件，保证字节级保真

## 常见错误示例

### 1. 旧通知格式

**错误**（已废弃）:
```text
Old shorthand: two lines without HERMES_STATUS/HERMES_REPORT_PATH keys
```

**正确**:
```
HERMES_STATUS: REPORT_WRITTEN
HERMES_REPORT_PATH: /some/path.md
```

### 2. Markdown 报告代替 canonical 报告

**错误**:
```markdown
# Report for goal X

## Summary
Everything worked.
```

**正确**:
```
BEGIN_HERMES_REPORT
goal_id: my-project
iteration: 1
status: PASS
summary: make validate passed
changed_files: none
commands_run: - make validate
validation_result: exit code 0
commit: abc1234
report_path: ~/.agent-loop/goals/my-project/hermes-reports/001.md
issues: none
recommendation: No further action
END_HERMES_REPORT
```

### 3. 范围扩大

**错误**:
```
# 命令说：make validate
# Hermes 执行：
make validate   # 通过
make test       # 未请求，可能写文件
make build      # 未请求，可能写文件
```

**正确**:
```
# 命令说：make validate
# Hermes 执行：
make validate   # 通过 → 停止
```

### 4. 多命令输出

**错误**（OpenClaw plan 模式）:
```
BEGIN_OPENCLAW_DECISION
...
END_OPENCLAW_DECISION

BEGIN_HERMES_COMMAND
command_type: inspect
...
END_HERMES_COMMAND

BEGIN_HERMES_COMMAND
command_type: implement
...
END_HERMES_COMMAND
```

**正确**:
```
BEGIN_OPENCLAW_DECISION
...
END_OPENCLAW_DECISION

BEGIN_HERMES_COMMAND
command_type: inspect
...
END_HERMES_COMMAND
```

## 验证方法

运行验证脚本：

```bash
make validate-skills
```

或手动检查：

```bash
bash -n scripts/validate-skills.sh
scripts/validate-skills.sh
```

## 版本

1.0.0 — 2026-06-14
