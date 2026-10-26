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

跨主机通信为**已有 SSH alias 的加密端口转发**，不直接开放公网 TCP/MCP 端口。Hub 独立令牌位于 `~/.config/cx-pan/token`（不进 Git/Notion）。Worker 使用 Claude CLI：`--permission-mode dontAsk --allowedTools Read,Glob,Grep --disallowedTools Bash,Edit,Write,... --no-session-persistence`；绑定只读仓库目录，最多四轮、单请求预算上限默认 0.75 美元（可由 CX_PAN_CLAUDE_MAX_BUDGET_USD 调整）。不自动重启 Hermes/OpenClaw。

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


## P2（2026-10-26）：只读 Gateway 状态适配器与执行心跳

新增两个允许的目标：
- `hermes.health.local` / capability `gateway.health`：调用 systemd 的只读 `is-active` 和 Hermes CLI `--version`。**不启动 Hermes 模型、不访问文件或调用 Hermes Gateway 工具**。
- `openclaw.health.local` / capability `gateway.health`：调用同样的只读 service status 和 OpenClaw CLI `--version`，选择系统中已存在的 Node 24 可执行路径。**不进入 OpenClaw agent turn**。

使用：

```bash
python3 bridge/client.py submit --target hermes.health.local --goal '只读查看 Hermes Gateway 状态'
python3 bridge/client.py submit --target openclaw.health.local --goal '只读查看 OpenClaw Gateway 状态'
```

与 Claude/echo 共用本地 Worker，每约 20 秒领取任务。运行中的 Worker 也每约 20 秒发送一次 `POST /v1/workers/heartbeat`，Hub 检查 task_id + attempt_id + worker_id 是否一致。查询 `GET /v1/tasks/<id>` 返回 `execution_health`：`WAITING_FOR_WORKER`、`RUNNING_HEARTBEAT_OK`、`STALE_NEEDS_REVIEW`（连续 180 秒没有心跳）或 `FINISHED`。`STALE_NEEDS_REVIEW` **不意味着已经失败**，更不会自动再跑一次：避免超时导致重复执行或付费。

本轮尝试模型级适配时，Hermes 的 `chat --safe-mode --toolsets none` 在配置/模型参数路径分别遇到不兼容参数、未提供模型、provider `invalid_params`；OpenClaw `agent exec` 使用独立只读 config/模型调用进程退出码为 137，未取得输出且未查明是否资源终止。为避免干扰用户本地正在进行的任务，**本阶段不将两者的推理/命令执行功能标记为已接入**。只做 Gateway 存活与版本查询。后续再次开启模型执行前，需先完成明确资源预算、权限与工具面隔离的单独实机验收。


**P2 模型失败记录：** P2 task_id `e79170d9-596b-4c6c-879c-ad1a7847f82f` 运行期间 Hub 多次报告 RUNNING_HEARTBEAT_OK，但最终 Claude Code exit 1，Hub 正确记录 FAILED。当前已将后续 CLI 异常输出调整为只记录 subtype/退出码/字节数，不直接保存长段 stdout，不把此任务当作模型分析成功。


## P3：三阶段就绪验收与可重放流程（2026-10-26）

P3 不把 Hermes/OpenClaw Gateway 在线冒充模型级执行。为了在模型调用尚未打通时提供实际可用的流程，新增：

- `bridge/workflow.py`：串行提交固定阶段，同一 workflow_id 对应稳定的 idempotency_key；每阶段必须 COMPLETED 才继续。结果保存在 `~/.local/state/cx-pan/workflows/<workflow_id>.json`，包含任务 ID、真实 run_id 和结果摘要。中断后重新启动同 ID 将复用旧任务，不盲目重复执行。
- `repo.validate.local`：独立固定执行器只对已批准的 agent-loop 仓库运行 `python3 -m unittest discover -s tests -q`；该阶段不调用任何模型、不接受任意 shell 命令。
- 后续检查 `hermes.health.local` 和 `openclaw.health.local`，依次获得真实 Gateway 状态；三阶段串联是“测试/健康检查”工作流，不是三个模型彼此审稿。
- 可选 `--with-claude` 会首先调用已有 Claude Code 只读研究任务，成功后再开始三个验证阶段；Claude 失败则停止并保留 FAILED 回执，不自行重试/掩盖错误。

真实执行：

```bash
cd ~/workspace/projects/agent-loop
python3 bridge/workflow.py --workflow-id cxpan-p3-readiness-20261026
python3 bridge/workflow.py --workflow-id cxpan-p3-readiness-20261026
# 同 ID 的第二次调用只复用原 COMPLETED 结果。
python3 bridge/workflow.py --workflow-id my-p3-claude-check --with-claude
```

实机就绪流程 `cxpan-p3-readiness-20261026` 三个任务全部 COMPLETED：
- `8233dd3b-3cee-427d-8c4f-48e4510791ea`：固定仓库校验 26 tests PASS。
- `2328968f-c6e5-42f9-b617-27a2c15fa989`：Hermes Gateway active。
- `40edf608-6ec9-4c99-8812-af9f6ea5116d`：OpenClaw Gateway active。
- 同一 workflow_id 再次执行时 3 项 duplicate=true；云端事件每个任务仅出现一次 QUEUED、CLAIMED、COMPLETED。

P3 模型诊断：本地 Hermes 参数 `-t none` 被拒绝，提示 unknown/invalid toolset；省略 -t、使用 safe-mode + 明确 MiniMax 模型后进程 65 秒超时，未得到回答，日志出现 managed_worker_failed。本地 OpenClaw 使用原生 Gateway operator session 的单轮 tool-free prompt，也在限定时间内超时；Gateway 记录 worker task timed out。MiniMax api.minimaxi.com 的 DNS/TLS 可连接（HEAD 返回 404，不代表认证/推理成功）。模型调用阻塞不等于 CX-PAN transport 阻塞；未修改原生 Gateway、模型或路由配置。

**尚未验收：** Hermes/OpenClaw 模型级工作单、不同 Agent 实际读取彼此结果做判断、通用 Remote MCP、Dots/Funes/Muse 接入。


**P3 Claude 预算实验：** 使用原 0.20 美元上限的 Claude 阶段 task_id `3016310a-f9e4-4d8a-86e4-283f1942b58f` 真实返回 `FAILED`，错误类别为 `error_max_budget_usd`。原任务保持失败，不自动重试；新增 `CX_PAN_CLAUDE_MAX_BUDGET_USD`，默认 0.75 美元，以新 workflow ID 独立重验。该参数是上限，不是实际花费凭证。


## P3 完整四阶段实测（2026-10-26）

使用 `CX_PAN_CLAUDE_MAX_BUDGET_USD=0.75` 默认上限后，新 workflow `cxpan-p3-claude-retry-20261026` 四阶段均 COMPLETED：
- Claude Code 真实只读分析任务 `c520ab0b-778b-4eb3-8508-ec8909cba422`、session/run_id `8030983d-0f6a-4db8-aebe-7d190af23878`，约 2551 个正文字符；
- 固定仓库校验 `3aff96f0-9310-4d80-87b2-8861e4d527df`，PASS；
- Hermes Gateway 状态 `225267ba-8a51-436a-8c32-b9259eb6e7a6`，active，不涉及模型；
- OpenClaw Gateway 状态 `148c29dd-83ef-497c-a7f5-24259a631a64`，active，不涉及模型。

重新用相同 workflow_id 跑完整流程，4 项均 duplicate=true，没有二次调用 Claude 或测试。最初使用 0.20 美元上限的 `cxpan-p3-claude-readiness-20261026` 保持 FAILED 历史不覆盖。Hermes/OpenClaw 真正模型级任务仍不可标为 PASS；详见集成总纲。
