# agent-loop 中文指南

[![CI](https://github.com/conanxin/agent-loop/actions/workflows/ci.yml/badge.svg)](https://github.com/conanxin/agent-loop/actions/workflows/ci.yml)

OpenClaw ↔️ Hermes 双 Agent 文件中继循环协议。

## Skills Quick Install

```bash
./scripts/install-all.sh
```

单独安装 Skills：

```bash
./scripts/install-skills.sh
```

## 与 CX-PAN 多 Agent 协作的关系（2026-10-26）

agent-loop 最初只解决 OpenClaw 规划/审核 与 Hermes 执行/汇报 之间的可靠文件交接。它不是多 AI 任务编排平台，CLI 不会自动执行命令、启动常驻服务或直接调用外部 API。

本轮源码增强了命令/报告/决策的身份与轮次校验、隔离的错误案例测试，以及可被其他 Agent 读取的只读 JSON 状态。调用 `python3 bin/agent-loop-status-json --all` 或 `make contract-test` 即可查看和验证。

跨电脑文件路径默认不可远程读取；真正跨云端执行需由独立 CX-PAN Hub/Adapter 提供，不能把 JSON 状态当作网络互联已经完成。历史兼容边界详见 [CX-PAN 集成设计](docs/CX_PAN_INTEGRATION.md)。

2026-10-26 已在可选的 `bridge/` 中新增并实测云端任务队列 + 本地 Claude Code 只读 Worker，原手工 relay 不变。详见 [bridge 使用与验收](bridge/README.md)。 P2 已增加 Hermes/OpenClaw 只读 Gateway 状态查询与任务心跳；不能将状态检查等同于模型级执行。


## P8 ChatGPT OAuth 授权服务（2026-10-27）

现已在腾讯云实际部署基于官方 MCP Python SDK 的 OAuth 授权码/PKCE S256 服务。ChatGPT 入口通过标准受保护资源元数据完成发现，Token 限定 `tasks:safe` 和正确资源地址。生产合成客户端已完成 DCR → Owner 授权 → OAuth Token → 真正 MCP Echo → 刷新 → 撤销，未保留活动测试 Token。DCR 默认关闭，仅用户在可信终端短时开启；不改变 Claude Chat 独立 Bearer 凭据。

**真正的 ChatGPT Plugins UI 尚需本人安装并显式授权；Claude Chat 自定义连接器 UI 也还需本人连接。** 详见 [P8 OAuth 连接与运维手册](bridge/P8_OAUTH_OPERATIONS.md)，不要将合成测试通过误称为两个聊天界面已安装成功。

## P7 专用 MCP 接口（2026-10-26）

`bridge/mcp_gateway.py` 已经通过腾讯云已有 HTTPS 站点提供两条独立、Bearer 保护的 MCP 测试入口，ChatGPT 专用测试凭据与 Claude 凭据分开，四个工具只允许安全任务查询与公开源文采集。真实 HTTPS 客户端双边各完成一次 Echo 往返；Claude MCP 客户端还能读取 ChatGPT MCP 客户端的安全任务。**真正 Claude Chat UI 需要用户连接；ChatGPT 原生 Plugins 还需 OAuth 2.1，不能以 API-key 测试成功冒充原生安装成功。** 详见 [P7 MCP 使用和权限说明](bridge/README.md)。

## P6 原始文档双 Agent 核验（2026-10-26）

已在既有 CX-PAN 桥接层实现受限制的主文档证据胶囊：仅对仓库白名单中公开的 `README.md`、`docs/SPEC.md`、`docs/SCHEMAS.md` 采集原始 UTF-8 文本与 SHA-256；本地 Hermes、腾讯云 OpenClaw 两个审核者可收到同一份经 Hub 核验的封存原文，并引用具体行号。

已实机完成 `docs/SPEC.md` 双 Agent 核验、云端来源 SHA-256 比对、重复请求不重复模型执行。使用 `python3 bridge/source_review.py --workflow-id my-source-001 --source docs/SPEC.md --claim '请用行号说明协议中手动中继的依据。'^。不支持任意读取 NAS/私有档案，未开放公网 Remote MCP；详见 [P6 源文证据与限制](bridge/README.md)。

## P5 三模型真实协作（2026-10-26）

已通过 ChatGPT/CXRE、Claude Code（本地）、Hermes（本地）、OpenClaw（腾讯云）的实际研究结果交接。指定已完成的 Claude task ID 后，`python3 bridge/review_chain.py --source-task-id <id>` 自动执行 Hermes 和云端 OpenClaw 两级受限文本复核，完整父任务 ID、原始正文 SHA-256、执行 ID 与终态由云端 SQLite 记录，重复执行复用结果。**这是转交研究文字，不等于三个模型共同读取了原始文件。** [完整 P5 验收与命令](bridge/README.md)。

## P4 双模型协作（2026-10-26）

已实测 ChatGPT 经 CX-PAN Hub 交给本地 Hermes 的纯文本模型任务；已将一个真实 Claude Code 报告自动交给 Hermes 独立复核并返回结果。使用 `python3 bridge/handoff.py --source-task-id <claude_task_id> --wait`。重复同一来源不会创建第二次模型调用。Hermes 工具集只开放 clarify，不执行本地命令。OpenClaw 模型任务仍未通过，不能把 Gateway 在线等同模型能力已接入。详细证据见 [Bridge P4](bridge/README.md)。

## P3 就绪检查

现可运行 `python3 bridge/workflow.py --workflow-id my-p3-check-001`，顺序执行固定仓库测试和两个 Gateway 的只读状态查询；结果保存在任务状态账本，同一 ID 再跑不会重复执行。可用 `--with-claude` 先加入 Claude 只读分析。这不是 Hermes/OpenClaw 模型级执行能力的验收。 另已通过 `--with-claude` 的真实 Claude 参与的四阶段工作流；详见 [bridge 实机回执](bridge/README.md)。

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

## 持续集成

仓库在 `.github/workflows/ci.yml` 包含 GitHub Actions 工作流，每次 push/PR 到 main 时运行。它强制执行：

- 所有脚本和 bin 工具的 `bash -n`
- `scripts/validate-skills.sh` 校验 skill 内容
- `make validate` 检查项目结构和密钥
- `scripts/smoke-test.sh` 在隔离的 `AGENT_LOOP_HOME` 中运行端到端测试

README 顶部的 CI 徽章反映当前构建状态。

本地运行相同检查：

```bash
chmod +x scripts/*.sh bin/agent-loop-*
make validate
./scripts/validate-skills.sh
AGENT_LOOP_HOME=/tmp/agent-loop-smoke ./scripts/smoke-test.sh
```

## 5 分钟快速安装

### 一键安装

```bash
git clone https://github.com/conanxin/agent-loop.git
cd agent-loop
./scripts/install-all.sh
export PATH="$HOME/.agent-loop/bin:$PATH"
```

### Skills 单独安装

```bash
./scripts/install-skills.sh
```

## 常见协议漂移问题

| 问题 | 原因 | 修复 |
|---|---|---|
| 旧通知格式（`REPORT_WRITTEN\n/path`） | 使用了简写 | 使用 `HERMES_STATUS: REPORT_WRITTEN` + `HERMES_REPORT_PATH: <path>` |
| Markdown 报告代替 canonical | Hermes 写了 `# Report` | 使用严格 11 字段 `BEGIN_HERMES_REPORT` |
| 范围扩大（`make validate` → `make test`） | Hermes 跑了额外命令 | 指定命令通过后停止 |
| 多个 `BEGIN_HERMES_COMMAND` 块 | OpenClaw plan 模式输出了 inspect + implement | 只输出一个主命令块 |
| 错误的 judge prompt 格式 | 路径写在同一行 | 使用 `/skill hermes-agent-loop judge-path` + `report_path: <path>` 分两行 |

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
