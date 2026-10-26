# CX-PAN P1｜ChatGPT → Claude Code 的最小真实任务链

本目录是 `agent-loop` 之外的可选**跨主机任务适配层**。原有 `bin/agent-loop-relay`、`~/.agent-loop/goals`、Hermes/OpenClaw Gateway 均不需要修改。已在 2026-10-26 的 Windows/WSL2 + 腾讯云 Ubuntu 环境实施基本版本。

## 它解决什么问题

你在 ChatGPT（经现有 CXRE）发出一个任务，腾讯云记录任务，Windows/WSL2 的常驻 Worker 主动领取，把任务交给已登录的 Claude Code，只读读取 `agent-loop` 仓库，完成后将正文与 `run_id` 写回云端。ChatGPT、Claude 或另一经授权的 Agent 可以通过同一 CLI 查询结果，避免复制聊天内容。

这不是 Claude 网页聊天的远程会话唤醒，也不是一个已经公开的 MCP/A2A 服务器。Claude 的执行目标是本地 Claude Code CLI。

## 组成

- `hub.py` — 腾讯云上监听 `127.0.0.1:18487` 的 Python 标准库 HTTP + SQLite 任务账本（无需 pip、Redis、Docker）。
- `client.py` — 你在 ChatGPT/Claude 可达的 WSL2 执行的命令行入口：submit/status/result/agents。
- `worker.py` — 本地向云端主动领单，当前支持 `echo.local` 和 `claude.code.local`，后者仅可对 allowlist 仓库做只读检查。
- `systemd/` — 云端 Hub、本地 SSH 通道、本地 Worker 三个独立 service 文件。

跨主机通信为**已有 SSH alias 的加密端口转发**，不直接开放公网 TCP/MCP 端口。Hub 独立令牌位于 `~/.config/cx-pan/token`（不进 Git/Notion）。Worker 使用 Claude CLI：`--permission-mode dontAsk --allowedTools Read,Glob,Grep --disallowedTools Bash,Edit,Write,... --no-session-persistence`；绑定只读仓库目录，最多四轮、单请求预算上限 0.20 美元。不自动重启 Hermes/OpenClaw。

## 实际使用：提交 Claude 任务

```bash
cd ~/workspace/projects/agent-loop
python3 bridge/client.py submit \
  --target claude.code.local \
  --project-id CX-PAN \
  --goal '请分析 README.md，解释 agent-loop 原来的目标，并给出下一步建议'
```

客户端会返回新的 `task_id`。用该任务 ID 查询：

```bash
python3 bridge/client.py status <task_id>
python3 bridge/client.py result <task_id>
python3 bridge/client.py agents
```

同一任务重复提交可显式传 `--idempotency-key`；重复 ID + 同内容返回原任务，重复 ID + 不同内容返回 409。一个待领取任务只能被一个 Worker 领取；其结果只允许当前 claim 的 `attempt_id` 和 `worker_id` 回报。服务重启后 SQLite 保留任务状态，但中断于 RUNNING 的任务暂不自动重跑，避免重复执行或付费；这是下一阶段的重要工作。

## 已实施部署位置与接口边界

- 腾讯云 Ubuntu：`%h/cx-pan-hub/hub.py`、`%h/.config/cx-pan/token`、`%h/.local/share/cx-pan/tasks.sqlite3`、用户 systemd `cx-pan-hub.service`。只监听 loopback，工作内存约 10–15 MiB。
- 本地 WSL2：`cx-pan-ssh-tunnel.service` 持续通过 `ssh tencent` 转发 `127.0.0.1:18487`，`cx-pan-readonly-worker.service` 每 20 秒领取任务。都属于独立新增服务；没有改造旧网关。
- 授权 API：`POST /v1/tasks`、`GET /v1/tasks/{task_id}`、`GET /v1/tasks/{task_id}/result`、`GET /v1/agents`、`POST /v1/workers/claim`、`POST /v1/workers/report`。健康检查 `GET /healthz`，除健康检查外接口需要 Bearer。
- 当前任务目标只有 `echo.local` 和 `claude.code.local`，并没有 Grok、Muse、Funes、Hermes/OpenClaw 的任务执行 Adapter。

## 2026-10-26 首轮真机验收

1. **Echo 跨主机**：ChatGPT 通过 CXRE 提交任务到腾讯云 SQLite，WSL2 Worker 领取并返回 `ECHO_OK`，提交相同 idempotency_key 不重做；云端审计仅记录一条 QUEUED、CLAIMED、COMPLETED。
2. **Claude Code 真实执行**：ChatGPT 提交只读分析请求，Worker 调用已登录的 Claude Code v2.1.118，读取 README/协议/集成文档并返回真实中文分析、文件路径、Claude run/session ID，结果在云端为 COMPLETED。
3. **常驻 Worker 无需人工启动**：启用 `cx-pan-readonly-worker.service` 后，新提交的 echo 任务自动领取完成；再次提交 Claude 只读任务，系统自己调用 Claude Code 并写回结果。两次均可由 ChatGPT 客户端查询。
4. **本地纯代码回归**：原 12 项协议测试 + 新 4 项 Hub/HTTP 测试 = 16 项 PASS；验证幂等冲突、领单唯一性、拒绝错误 claim、HTTP 鉴权以及 API 回执。
5. **范围限制**：未验证 Claude Chat 在浏览器中通过其 CXRE 工具主动提交（但此前配置的 CXRE Claude 服务运行），未实现 MCP/A2A 公开适配、GitHub 自动部署、文件工件跨机传输、断点任务重领、统一人类审批、dots/Funes/Muse 事件闭环。

## 与之前研究的使用场景对应

- **本地找书**：ChatGPT 发单，后续让 Everything/OpenClaw 只读查询本机文件，云端记录查询任务，结果返回；尚未开发该 Adapter。
- **跨硬盘与 NAS 管理**：Agent 分片扫描各盘并回报进度/异常，涉及删除或迁移则人工批准；尚未开发。
- **代码协作**：现已证明 Claude Code 的只读仓库分析可自动接单和回传；下一阶段可给 Hermes 受控执行和 OpenClaw 复核增加 Adapter。
- **古籍壁画研究**：Funes 发研究工作单、OCR/检索 Agent 产物和证据交接、Notion 校读记录；尚未开发。
- **有声书 Muse**：ChatGPT 提交章节/Profile，Muse 如无自动外部 API 则 PULL_ONLY，再做音频验收；尚未开发。
- **每日简报**：汇总 ledger 状态、失败和待审批任务，在用户启用的通知通道推送；尚未开发。

## 后续最短任务

P2：在受控能力清单中接入 Hermes 和 OpenClaw Adapter（先只读），并增加实际 worker 心跳/失败后状态恢复；P3：加一个给 ChatGPT/Claude 都能调用的受限远程 MCP 工具层；P4：Notion 只写经过验证的研究结论、工件索引及用户批准；此后再接 Dots/Funes/Muse、A2A 等。

**不要**把可通过本地 CXRE 和 CLI 提交任务误说成已支持外界直接向 ChatGPT/Claude 网页聊天推送消息。


## 离线排队的补充实测

停掉本地专用 Worker 后提交 echo，保持 QUEUED；重启云端专用 Hub 后状态仍 QUEUED；重新启动 Worker 后自动转为 COMPLETED，正文正确。这仅证明**尚未领取的任务**能跨重启保存，不能据此宣称执行中任务可安全自动重试。
