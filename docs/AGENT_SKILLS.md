---
title: Agent Skills 指南
version: 1.0
---

# AGENT_SKILLS.md

## 概述

agent-loop 包含两个核心 skill，分别供 OpenClaw 和 Hermes 使用。

## OpenClaw Skill: hermes-agent-loop

**路径**: `skills/openclaw/hermes-agent-loop/SKILL.md`

**功能**:
- 生成符合规范的 `BEGIN_HERMES_COMMAND` 命令文件
- 提供 `judge-path` 子命令，用于读取 Hermes 的 canonical report 并做出判断
- 生成 `BEGIN_OPENCLAW_DECISION` 决策文件

**安装位置**:
```bash
${OPENCLAW_SKILLS_DIR:-$HOME/.openclaw/workspace/skills}/hermes-agent-loop/SKILL.md
```

**使用方式**:
```bash
# 在 OpenClaw 中调用
/skill hermes-agent-loop judge-path
report_path: ~/.agent-loop/goals/my-project/hermes-reports/001.md
```

## Hermes Skill: openclaw-command-executor

**路径**: `skills/hermes/openclaw-command-executor/SKILL.md`

**功能**:
- 解析 `BEGIN_HERMES_COMMAND` 命令文件
- 执行指令并记录结果
- 生成符合规范的 `BEGIN_HERMES_REPORT` 报告文件
- 通过 `agent-loop-relay --decision-path` 处理 OpenClaw 的决策

**安装位置**:
```bash
${HERMES_SKILLS_DIR:-$HOME/.hermes/skills}/openclaw-command-executor/SKILL.md
```

**使用方式**:
```bash
# 在 Hermes 中执行命令后
agent-loop-relay --decision-path my-project ~/.agent-loop/goals/my-project/openclaw-decisions/001.md
```

## 为什么 Telegram 只承载轻量通知

| 问题 | 解决方案 |
|---|---|
| Token 限制 | 文件系统无限制 |
| 格式漂移 | 严格的 BEGIN/END markers |
| 无法版本控制 | Git 管理 |
| 无法 diff | 文本文件可 diff |

Telegram 只发送:
```
HERMES_STATUS: REPORT_WRITTEN
HERMES_REPORT_PATH: ~/.agent-loop/goals/my-project/hermes-reports/001.md
```

所有结构化数据都在文件中。

## 手动验证 Skills

### 验证 OpenClaw Skill

```bash
cat ${OPENCLAW_SKILLS_DIR:-$HOME/.openclaw/workspace/skills}/hermes-agent-loop/SKILL.md
# 应包含: judge-path, BEGIN_OPENCLAW_DECISION schema, 状态映射表
```

### 验证 Hermes Skill

```bash
cat ${HERMES_SKILLS_DIR:-$HOME/.hermes/skills}/openclaw-command-executor/SKILL.md
# 应包含: BEGIN_HERMES_COMMAND 解析, BEGIN_HERMES_REPORT 生成, 安全边界
```

## 快速开始

1. 安装 skills:
   ```bash
   ./scripts/install-skills.sh
   ```

2. 验证安装:
   ```bash
   ls -la ${OPENCLAW_SKILLS_DIR:-$HOME/.openclaw/workspace/skills}/hermes-agent-loop/
   ls -la ${HERMES_SKILLS_DIR:-$HOME/.hermes/skills}/openclaw-command-executor/
   ```

3. 开始使用:
   - OpenClaw: 使用 `/skill hermes-agent-loop` 生成命令
   - Hermes: 执行命令后使用 `agent-loop-relay --report-path` 记录报告
