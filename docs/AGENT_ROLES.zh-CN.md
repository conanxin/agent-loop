---
title: Agent 角色定义
version: 1.0
---

# AGENT_ROLES.zh-CN.md

## 四个角色

| 角色 | 名称 | 职责 | 禁止行为 |
|---|---|---|---|
| **OpenClaw** | Planner / Judge | 规划任务、生成命令、评审报告 | 不执行命令、不修改项目代码、不伪造报告 |
| **Hermes** | Executor / Reporter | 执行命令、生成报告 | 不做规划、不做评审、不扩大执行范围 |
| **User** | Human Gate | 审批、监督、决策 | 不替代 Agent 执行、不绕过审批流程 |
| **Relay** | Local File State Machine | 管理文件状态、推进状态机 | 不自动执行命令、不修改项目代码 |

## 角色详解

### OpenClaw = Planner / Judge

**能做什么**:
- 分析用户需求，生成 `BEGIN_HERMES_COMMAND`
- 评审 Hermes 的 `BEGIN_HERMES_REPORT`
- 输出 `BEGIN_OPENCLAW_DECISION`（DONE / NEXT_COMMAND / REPAIR_COMMAND / BLOCKED / NEEDS_HUMAN_REVIEW）
- 生成 `judge-path` 提示

**不能做什么**:
- 执行 shell 命令
- 修改项目文件
- 创建伪造的 commit hash 或测试结果
- 在 plan 模式输出多个可执行的 command block

### Hermes = Executor / Reporter

**能做什么**:
- 读取 `BEGIN_HERMES_COMMAND` 并执行
- 运行测试、验证、检查
- 生成严格的 `BEGIN_HERMES_REPORT`（11 字段）
- 通过 Telegram 发送两行通知

**不能做什么**:
- 规划下一步任务
- 评审自己的报告
- 扩大执行范围（例如 `make validate` 后运行 `make test`）
- 用 Markdown 代替 canonical report

### User = Human Gate

**能做什么**:
- 审批 `requires_human_approval: true` 的决策
- 查看报告和决策文件
- 手动推进状态机（`--mark-dispatched`, `--mark-judging`）
- 终止任务或要求重新执行

**不能做什么**:
- 替代 Agent 执行命令（绕过记录）
- 跳过审批流程
- 修改状态机文件直接

### Relay = Local File State Machine

**能做什么**:
- 管理 `~/.agent-loop/goals/<goal_id>/` 目录结构
- 推进 `state.json` 状态
- 打印命令和提示供人类复制
- 验证决策文件格式

**不能做什么**:
- 自动执行命令
- 自动调用 OpenClaw 或 Hermes
- 修改项目代码
- 发送 Telegram 消息

## 协作流程

```
User 提出目标
    ↓
OpenClaw [plan] → 生成 DECISION + COMMAND
    ↓
Relay 记录状态 → 等待人类确认
    ↓
Human 复制 COMMAND 到 Hermes
    ↓
Hermes [execute] → 生成 REPORT
    ↓
Hermes 发送 Telegram 通知（2 行）
    ↓
OpenClaw [judge-path] → 读取 REPORT → 生成 DECISION
    ↓
如果 DONE → 结束
如果 NEXT_COMMAND → 生成下一个 COMMAND
如果 BLOCKED → 等待人类介入
```

## 为什么这样设计

1. **分离关注点**: OpenClaw 负责思考，Hermes 负责执行，避免单一 Agent 既当裁判又当运动员
2. **人类可控**: 每个关键节点都有人类审批机会
3. **文件保真**: 报告通过文件系统传递，避免 Telegram 文本变形
4. **状态可追溯**: `state.json` 记录完整状态链，便于审计和调试

## 常见角色混淆

| 混淆 | 后果 | 预防 |
|---|---|---|
| OpenClaw 执行命令 | 绕过记录，无法审计 | skill 明确禁止 |
| Hermes 规划任务 | 可能生成不可执行的命令 | skill 明确禁止 |
| Hermes 扩大范围 | 修改未请求的文件 | skill 明确禁止 |
| Relay 自动执行 | 失去人类控制 | 设计为只读打印 |
| User 跳过审批 | 安全风险 | 默认 `requires_human_approval: true` |

## 验证

检查角色定义是否被遵守：

```bash
# 检查 OpenClaw skill 是否禁止执行
grep -q "never executes" skills/openclaw/hermes-agent-loop/SKILL.md

# 检查 Hermes skill 是否禁止规划
grep -q "NEVER Planner" skills/hermes/openclaw-command-executor/SKILL.md

# 检查 Hermes skill 是否禁止扩大范围
grep -q "do not expand scope" skills/hermes/openclaw-command-executor/SKILL.md
```

## 版本

1.0.0 — 2026-06-14
