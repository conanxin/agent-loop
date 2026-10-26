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

## P4｜真正的 Claude → Hermes 双模型审查（2026-10-26）

P4 不再停留在 health 检查：本地 Hermes Agent v0.22.5 的 `hermes chat -q` 单次会话容易因为旧版 Gateway `session.create` 返回 `invalid_params`；根据上游 issue #139035/#139160 的解决线索，独立验证了 `hermes -t clarify -z` 受限的一次性模型回应，输出 `HERMES_P4_OK`，进程 exit 0、没有文件/终端工具。此实测证明当前 Hermes 模型可用，不需要更改 Hermes 原生 Gateway 配置。

独立模型适配器 `hermes.model.local` / capability `text.review` 通过 `bridge/worker.py` 使用 Hermes CLI 列表参数调用（无 shell），工具集只含 `clarify`。Hub 把文本写入数据库并返回 `COMPLETED`；它不能直接读取本地仓库、执行测试或修改 NAS 文件。`run_id=hermes-oneshot:<uuid>` 是 **CX-PAN Worker 生成的调用 ID**，不是 Hermes Provider 的原生 session/run ID。

本轮两个 Hermes 模型任务：
- 简短任务 `52620ba0-ce9d-4eb5-bb83-8eae57a05624` → COMPLETED，Hermes 根据材料审慎提示不要把输出标记当作真实验收；run_id `hermes-oneshot:831ffa14-c2f9-4076-ac6c-aafc257e0154`。
- **Claude → Hermes 真正跨模型复核：** 从历史 Claude 真实研究任务 `c520ab0b-778b-4eb3-8508-ec8909cba422` 读取 `COMPLETED` 报告及 Claude session `8030983d-0f6a-4db8-aebe-7d190af23878`，自动创建 Hermes 复核 task `d00acdaa-4595-4655-86dc-0550a336e8a5`，最终 COMPLETED，Hermes 按收到的 Claude 材料标出可支持论点、不确定项和下一步核实建议，明确不假装自己访问过原始文件；Worker 调用 ID `hermes-oneshot:42413953-4670-48ee-9b1e-30f318fee317`。
- 重复执行同一个 `source_task_id` 复核，返回原 task_id，`duplicate=true`。两次 Hermes 任务各自只有 1 个 QUEUED、1 个 CLAIMED、1 个 COMPLETED 事件。
- 由于上游 Claude 任务属于 P3 历史快照，其部分结论在 P4 已过期；Hermes 的复核**只针对收到的引文**，本项目最终状态应以 CX-PAN Ledger、当前 Git 和最新 Notion P4 验收为准。

操作：

```bash
cd ~/workspace/projects/agent-loop

# 直接让 Hermes 通过 Hub 做纯文本独立复核
python3 bridge/client.py submit --target hermes.model.local   --goal '请复核这段研究摘要中的证据与不确定项'

# 将一个已经 COMPLETED 的 Claude Code 报告交给 Hermes 二次复核
python3 bridge/handoff.py   --source-task-id c520ab0b-778b-4eb3-8508-ec8909cba422 --wait

# 同一上游任务再次调用只取原任务，不触发第二次模型调用
python3 bridge/handoff.py   --source-task-id c520ab0b-778b-4eb3-8508-ec8909cba422
```

P4 **还未完成 OpenClaw 模型审查**。本轮缩减工具面的 `openclaw agent exec` 仍返回 137 且无 JSON 结果；相关 user cgroup `memory.events` 的 oom_kill=0、`systemd-oomd` 未运行、可访问内核日志未见匹配 OOM，因此不能把 137 确诊为内存不足。进一步排查需单独测隔离运行时、worker 生命周期或 Provider，并限制资源影响，不应重启正在使用的 Gateway。

模型排障参考：[Hermes CLI 旧版 issue #139035](https://github.com/NousResearch/hermes-agent/issues/139035)｜[Gateway 修复汇总 #139160](https://github.com/NousResearch/hermes-agent/issues/139160)｜[OpenClaw agent exec CLI](https://docs.openclaw.ai/cli/agent)。


## P5｜真正的三模型跨主机独立研究链（2026-10-26）

P5 已在真实云端与本地系统完成 **ChatGPT/CXRE → Claude Code（本地）→ Hermes（本地）→ OpenClaw（腾讯云）→ CX-PAN 结果查询**。两个模型接力过程自动由 CX-PAN Ledger/Worker 完成，没有人工复制/粘贴。OpenClaw 云端版本为 2026.10.3，使用 MiniMax M3.1 Flash + adaptive 思考模式；本地之前的 137/timeout 不再作为 P5 模型入口。

### 真实失败原因与成功入口

- 本地独立 OpenClaw 的进程 137 并无 OOM 核验依据；延长诊断也未取得模型回复。无关进程实验显示 GNU timeout 带 kill-after 可能返回 137，故不能直接把 137 归于内存。
- 云端第一次调用 `--thinking off` 失败，OpenClaw JSON 明确表示该 MiniMax 模型只允许 adaptive / ultra；修正为 `adaptive` 后，约 27 秒得到 `OPENCLAW_CLOUD_P5_OK`，`ok=true`、`status=ok`。
- 随后独立创建 `~/.openclaw/cxpan-p5-readonly.json5`（只有引用原配置和工具白名单，不复制明文密钥），通过根包含继承云端现有 MiniMax provider，并覆盖 `tools.deny=["*"]`、`tools.allow=[]`，测试模型 `OPENCLAW_CXPAN_SAFE_OK` 约 23 秒返回，未看到工具调用。云端 Gateway 配置/模型默认设置保持不变。

### 云端独立 Worker（非 Gateway 改造）

- 腾讯云运行 `cx-pan-cloud-openclaw-worker.service`，只领取 `openclaw.model.cloud` / `text.review` 类型的任务，直接访问腾讯云回环 `127.0.0.1:18487` 的受认证 Hub API。
- 受控 Python 程序 `bridge/cloud_worker.py` 调用固定 `openclaw agent exec --config ~/.openclaw/cxpan-p5-readonly.json5 --model minimax/MiniMax-M3.1-Flash --thinking adaptive --code-mode direct --json`；不使用 shell 拼接任务文本，不对外发送聊天信息。失败只记录有限退出码/错误类别，避免原始敏感输出。
- Worker 返回真实的 OpenClaw `sessionId`，在 Ledger 中以 `openclaw:<sessionId>` 呈现；这与 Hermes 的 `hermes-oneshot:<uuid>`（由 CX-PAN Worker 生成）是不同性质的标识。
- 原本的 WSL2 Worker 仍只执行本地 Claude、Hermes 和状态/固定测试任务，不会去争抢云端 OpenClaw 任务。

### P5 结构化来源证明

- 云端 SQLite 为 P5 新增独立的 `task_provenance` 表（保留旧 tasks/events 不做覆盖迁移），每条审核记录都具备不可变的父 task_id 和原文 SHA-256。
- 当子任务带 parent_task_id 和 source_sha256 入队时，Hub 核验父任务已 COMPLETED、项目相同、能力链合法（Claude→Hermes 或 Hermes→OpenClaw）、完整原始结果 SHA-256 匹配，且子任务确实引用源文本的开头；不满足直接拒绝。
- 相同 idempotency_key 不产生第二个工作单，错误正文/哈希和跨项目请求被拒绝。
- P5 `bridge/review_chain.py` 对已完成的 Claude 任务进行两个模型复核阶段。任何一步 FAILED/超时都停止；不自动重试副作用或付费模型任务。收到的审查只基于上游转交文字，不代表模型直接阅读/验证了原件。

### P5 真机成功回执

本轮复用了真实 Claude 来源 `c520ab0b-778b-4eb3-8508-ec8909cba422`（Claude run `8030983d-0f6a-4db8-aebe-7d190af23878`，2551 字符），然后连续执行：

1. Hermes P5 审查 `eff2d648-c73e-4aa8-a6a0-a441727eaf42`，`COMPLETED`、run `hermes-oneshot:601be788-2752-45ae-9c04-fa7bf80910d4`，生成 1672 字符分析。
2. 腾讯云 OpenClaw 审查 `0563cd89-d86f-4c5b-9aba-d0c9e278aad4`，`COMPLETED`、真实 session `8ccc3663-55bc-4fa0-9ede-04c678b9bbd6`，生成 2670 字符分析。
3. OpenClaw 明确把原始 Hermes 引文限定为待验证材料，区分了两条可在引文内部支持的判断、一条过时/未核实断言和后续文件/日志核查步骤。它没有假装已经读取文件。
4. 两个子任务的 parent_task_id 和 sha256 经独立 SQL 重算全部相符；三条任务各自只有一次 QUEUED/CLAIMED/COMPLETED。
5. 重新运行同一个 Claude 来源的 `bridge/review_chain.py`，Hermes/OpenClaw 均返回 `duplicate=true`，并重用同一个最终报告。

使用命令：

```bash
cd ~/workspace/projects/agent-loop
python3 bridge/review_chain.py   --source-task-id c520ab0b-778b-4eb3-8508-ec8909cba422   --stage-timeout 175

python3 bridge/client.py result 0563cd89-d86f-4c5b-9aba-d0c9e278aad4
```

### 尚未实现和后续

- OpenClaw 模型现在是**云端受限文本审查**，不是本地 OpenClaw 已恢复；本地独立执行 137/卡住仍单列问题。
- 三模型链路共享的是**特定工作单结果**，不是任意 AI 私人聊天可被外部唤醒，也不是各 Agent 全部私人记忆互通。
- Hermes 和云端 OpenClaw 都没有在这条复核任务中直接读取实际文件。要升级为真正多 Agent 独立证据验收，需新增明确授权的文件引用/只读检索 Adapter、SHA-256 跨主机工件服务和验证门。
- ChatGPT/Claude Chat 使用远程专用 MCP、Notion 任务完成时自动增量归档、Dots/Funes/Muse 等仍未部署；每项需单独真实验收。
- 三个模型处理的上游 P3 研究摘要含历史状态，当前权威运行状态以云端 Ledger + 本轮 Git/Notion P5 记录为准。

[OpenClaw 官方 agent exec](https://docs.openclaw.ai/cli/agent)｜[OpenClaw 工具拒绝策略](https://docs.openclaw.ai/gateway/config-tools/tool-policy)｜[配置包含](https://docs.openclaw.ai/gateway/config-secrets-env)
