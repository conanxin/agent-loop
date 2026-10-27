# agent-loop 原始目标复盘与 CX-PAN 接入边界（2026-10-26）


## 当前权威状态（2026-10-27 P9 更新）

- **私有 ChatGPT 插件已创建但未安装：** `CX-PAN v0.1.0`、scope USER、discoverability PRIVATE，入口 [打开插件](https://chatgpt.com/plugins/plugins_6ae016c0348881918f74bd2c023ab5fe)。通过官方插件包的 `mcp.json` 指向既有 `https://www.conanxin.com/cxpan/chatgpt/mcp`、OAuth DCR 与唯一 `tasks:safe`；不附带任何密钥。
- **OAuth 安全治理已增强：** 受信任 Owner 可查看已登记客户端、核对请求 callback/scope/到期时间、检索审计和按 client_id 撤销所有相关 access/refresh/codes/pending；DCR 新增窗口频率限制（30 分钟内最多 5 次），授权 pending 8/客户端、30/全局。OAuth AS metadata 现在明确发布公共客户端 `none` 与 secret_post/basic 三种受支持方法。MCP tools/list 中三个工具标 readOnlyHint=true，`task_submit_safe` 显示是幂等的队列写入。
- **实际协议验收：** 生产公网合成 OAuth 流程再次 PASS，临时 OAuth 测试客户端已删除，云端 Active Access=0、Active Refresh=0、registered client=0、pending request=0、DCR CLOSED。合成测试并不代表用户 ChatGPT/Claude Chat Web UI 已完成本人 OAuth 安装。
- **一条终端命令：** `python3 bridge/connect_chatgpt.py` 将在用户本人可信交互式终端中打开短时 DCR、核对浏览器一次性请求、明确 START 和 APPROVE 后完成授权，最后关闭 DCR。非交互终端/Agent 调用拒绝。完整手册见 `bridge/P9_CONNECTOR_OPERATIONS.md`。
- 下文 P0–P8 内容保留历史，不要将 P9 完成的插件**创建**写作已连接。P10 需要用户真实客户端 UI 操作、权限确认与实际调用回执。

## 当前权威状态（2026-10-27 P8 更新）

- **生产可用的 ChatGPT OAuth 端点已搭建：** 腾讯云现有 Caddy HTTPS 独立路由到回环 `cx-pan-oauth.service`（18489），标准发现 `/.well-known/oauth-authorization-server`、`/.well-known/oauth-protected-resource/cxpan/chatgpt/mcp`、授权 `/authorize`、Token `/token`、DCR `/register` 和撤销 `/revoke`。资源 MCP `cx-pan-mcp.service`（18488）同时支持 P7 旧凭据及经过 Resource/Scope/TTL/Revocation 验证的 OAuth access token。
- **安全边界：** OAuth 申请只有 `tasks:safe`，客户端注册默认关闭且需要 SSH Owner 临时开放；同意授权需用户从浏览器读 Request ID 并通过可信终端显式批准，没有公开的“点一下即批准”按钮。
- **生产合成客户端验收：** 真正公网 HTTPS DCR → S256 授权码 → 审批 → Token → MCP initialize / safe Echo 任务 COMPLETED → Refresh → Revocation；测试 Token 已全部吊销，云端有效 Access/Refresh 计数为零。
- **不能误报：** 当前并未观察真实 ChatGPT Plugins 用户界面或 Claude Chat 网页端完成连接。ChatGPT native UI 仍需要用户在 Plugins 中安装并授权；Claude 仍沿用 P7 独立 Bearer。该 P8 为 SDK-backed 自建 Auth 服务，CIMD 未实现，当前使用 DCR；在接私有文件或提升付费权限前需要专门安全审计。详见 `bridge/P8_OAUTH_OPERATIONS.md`。
- 下方 P0–P7 保留历史记录，以 P8 本节和对应 Notion 页面为最新阶段状态。

## 当前权威状态（2026-10-26 P7 更新）

- P7 已通过 Caddy 现有 TLS 站点部署两条独立、需要 Bearer 认证的标准 MCP Streamable HTTP 路径：`https://www.conanxin.com/cxpan/chatgpt/mcp`、`https://www.conanxin.com/cxpan/claude/mcp`。腾讯云后端 MCP 在回环 `127.0.0.1:18488`，核心 Hub 在 `127.0.0.1:18487`，没有开放额外公网端口；原网站首页及已有 Agent Gateway 状态正常。
- 仅暴露 agents_list、task_get、task_result、task_submit_safe 四个工具；后者限定 echo/公开原文采集、每日配额；客户端独立 token 的哈希存云端、明文只存本地模式 0600 的配置目录。两种客户端模拟器经真实 HTTPS 均完成 Echo 任务，Claude 客户端模拟器读取 ChatGPT 模拟器的安全任务，源文采集 `docs/SPEC.md` 再次验收通过。
- **客户端 UI 边界：** Claude Chat 的自定义 MCP 可由用户通过固定 Header 认证连接，但尚未在 Claude Chat 界面实际点击安装；ChatGPT 原生 Custom MCP 当前需要支持的 OAuth 2.1 认证流程，不能使用私有 API key 直接配置原生插件。ChatGPT 仍可使用已有 CXRE Personal；P8 优先处理 OAuth 或受支持 Secure MCP Tunnel。因此本次宣称的是“正式 HTTPS MCP 接口 + 模拟客户端实测”，不是两个消费版聊天客户端已正式连上。
- 本页 P0–P6 为历史快照，以本节和最新 Notion P7 进展页面为当前状态；P7 详细内容详见 bridge/README.md。

## 当前权威状态（2026-10-26 P6 更新）

- 已在 P5 三模型交接之外完成**同一原始文档的受限采集与 Hermes/OpenClaw 并行原文复核**；来源是公开 agent-loop `docs/SPEC.md`（5299 原始字节、176 行），本地封存 SHA-256 及云端 result SHA-256 均已实机验收。
- 三个实际任务分别为采集 `b288f972-bc0e-411c-bc3d-883531415bbb`、本地 Hermes 复核 `77233bfb-9d11-4711-bc53-963736f399b7`、腾讯云 OpenClaw 复核 `1c3c1509-690b-4a24-be35-2e745de8c2e8`，均 COMPLETED；两个 Reviewer 的 parent_task_id/sha256 均指向同一份来源。重新发起同 ID 均 duplicate=true，无二次模型执行。
- 引用范围自动检查：Hermes 13 处完整 `[docs/SPEC.md:Lx]` 行号引用、OpenClaw 1 处完整引用，均不越界。这个检查并非内容真伪或完整源代码验收，当前只允许白名单的 3 份公开文件。
- Hermes 与云端 OpenClaw 是通过**带 SHA 的封存原文**读取同一份材料，不能说两者直接登录本地磁盘；是否按规范实现，需要查看源代码和实机任务而非只看 SPEC。
- 独立 ChatGPT/Claude Chat Remote MCP、公网能力、跨私有 NAS 文件、Notion 全自动事件同步均未部署。此页 P0–P5 段落保留历史版本，以本节及最新 P6 验收为准。详细交付见 bridge/README.md。

## 当前权威状态（2026-10-26 P5 更新）

- **首次真正完成 Claude Code（本地）→ Hermes（本地）→ OpenClaw（腾讯云）的三模型研究文本自动交接。** 任务 ID 分别为 `c520ab0b-778b-4eb3-8508-ec8909cba422` → `eff2d648-c73e-4aa8-a6a0-a441727eaf42` → `0563cd89-d86f-4c5b-9aba-d0c9e278aad4`，全部 COMPLETED。
- **来源链验证：** Hub 新增独立 task_provenance(parent_task_id,source_sha256) 表；两级上游来源及原始文本 SHA-256 由 Hub 入队核验，事后直接读云端 SQLite 独立重算一致。重复执行同来源两阶段全部 duplicate=true，没有重做模型调用。
- **OpenClaw 云端突破：** 云端 OpenClaw 2026.10.3 MiniMax M3.1 Flash 使用 adaptive 思考模式得到真实回复；Cloud Worker 使用 pinned no-tools config（继承现有 MiniMax provider，但 deny all tools），模型返回 OpenClaw 原生 session ID。原有 OpenClaw Gateway 配置未改变。
- **保留边界：** 本地 OpenClaw headless 仍无成功模型回执；新的 OpenClaw 是云端受限文本 reviewer。三模型并未直接读取或核验所有源文件；它们审阅的是任务结果的引文，部分 P3 时间点材料已过时。完整回执详见 bridge/README.md。
- 下文旧 P0–P4 记录均为历史快照；以本节和最新 P5 Notion 阶段页作为权威状态。

## 当前权威状态（2026-10-26 P4 更新）

- **新突破：** Hermes v0.22.5 的受限模型响应通过 `hermes -t clarify -z` 真实返回 `HERMES_P4_OK`；CX-PAN 云端新增 `hermes.model.local` 并取得真实模型结果。已实际完成 **Claude Code P3 报告 → Hermes 独立文本复核** 的跨模型任务交接；复用同一上游 source_task_id 后，Hermes 不重复执行。
- **P4 Claude→Hermes 回执：** Claude source_task_id `c520ab0b-778b-4eb3-8508-ec8909cba422` → Hermes task_id `d00acdaa-4595-4655-86dc-0550a336e8a5`（COMPLETED）。Hermes 回答区分引文可支持论断和不可独立核验内容；不能把它当作直接文件读取的审计证据。
- **仍受阻：** OpenClaw 独立 headless 模型调用 exit 137；cgroup/oomd 无确定 OOM 证据。Hermes 模型执行属于工具集受限的纯文本评审，不等于 Hermes 有本地文件工具权限或能执行限定测试。
- 下方 P0–P3 文字保留历史原样以便追溯，以此节作为最新状态；详细实现和限制见 `bridge/README.md`。

## 当前权威状态（2026-10-26 P3 更新）

- **已部署并实机 PASS**：腾讯云 Hub + 本地 SSH 通道与 Worker；ChatGPT→Claude Code 只读分析→仓库固定测试→Hermes Gateway 只读健康检查→OpenClaw Gateway 只读健康检查。4 阶段 workflow ID `cxpan-p3-claude-retry-20261026`，均 COMPLETED，并验证同 ID 重跑全部 duplicate=true、不产生新执行。
- Claude 真实任务 `c520ab0b-778b-4eb3-8508-ec8909cba422`（run_id `8030983d-0f6a-4db8-aebe-7d190af23878`）成功。旧 `0.20` 美元任务上限曾导致 `error_max_budget_usd`，现改为可配置的默认 `0.75` 美元上限，不等于实际花费。
- **尚未 PASS**：Hermes 和 OpenClaw 的模型级任务、它们对 Claude 结果作模型审核、普通聊天 UI ↔ UI 的无授权自动唤醒、Muse/Funes/Dots 专用接入。
- Hermes P3 重新诊断发现 `-t none` 是无效工具集，修正后受限模型调用仍超时，日志 `managed_worker_failed`；OpenClaw Gateway 单轮请求超时，日志 `worker task timed out`。MiniMax endpoint DNS/TLS 可连接，不能据此证明模型响应正常。继续保留阻塞标签，未修改原有 Gateway/Provider 配置。
- **本页以下 P0/P1/P2 状态是历史快照**；后续进度以本节和带任务 ID 的最新实测为准。


## 1. 历史事实：从 Git 首次提交核对

- 源码根目录：~/workspace/projects/agent-loop
- 第一次提交：d93aef9（2026-06-14，Initial commit: agent-loop v1.0.0）
- 原始目标：让 **OpenClaw（规划、审核）** 与 **Hermes（执行、汇报）** 通过文件系统交接明确的命令、执行报告和审核决策；Telegram 只通知「报告已写入 + 路径」，不承载正文。
- 背景问题：聊天平台的长度限制、Markdown/格式漂移、乱序/不保证送达、无版本与审计链。
- 设计的关键边界：**manual relay，不自动调用任意 Agent、模型或外部 API；不创建 daemon；用户通过 mark-dispatched 显式确认已发送；通过 state.json 管理有穷状态机。**
- 原始状态：INIT → OPENCLAW_PLANNING/COMMAND_READY → DISPATCHED_TO_HERMES → HERMES_REPORT_WRITTEN → OPENCLAW_JUDGING → DONE/PARTIAL/BLOCKED/...；NEXT_COMMAND/REPAIR_COMMAND 返回规划。产物以 goal_id、iteration、canonical BEGIN/END blocks 关联。
- README 和 docs/SPEC.md、docs/SCHEMAS.md 为协议规范；独立仓库不应被直接替换成部署在公网的 Agent Gateway。

## 2. v1.0 旧系统的实际问题及本轮源代码调整

本轮先在隔离 AGENT_LOOP_HOME 进行验证，**不更新正在运行的 ~/.agent-loop/bin，不重启 Hermes/OpenClaw，不写任何现存 goal**。

1. 原始 smoke-test 的命令及报告都写死了错误 goal_id=SMOKE_TEST，报告的 report_path 还指向不存在的绝对路径，但以 state=DONE 通过测试。修复为变量化正确 goal_id 与实际报告文件路径。
2. relay 原先 --report-path 只判文件存在，就推进 HERMES_REPORT_WRITTEN。现在要求单一合法 BEGIN/END 区块、11 必填字段、goal_id 匹配、整数轮次一致、合法状态、report_path 必须指向实际绝对路径，错误情况拒绝状态变更。
3. relay 原先 decision 只验证部分字段，未验证 iteration 和布尔 requires_human_approval；现在严格检查两者，NEXT_COMMAND/REPAIR_COMMAND 将审批需求继承到新一轮。
4. relay 原先 state.iteration 多为 0，导致永远提示 001.md；现在从编号命令解析并记录迭代，数字 9/10 按数值选最新而非文件名字符串排序。
5. 检测已展示的命令被修改、已接收的报告被修改：SHA-256 不一致拒绝 dispatch/judge，须重新确认。
6. relay、set-state、show 拒绝越界 goal_id；relay 拒绝互斥标志的误用。
7. 修复仓库安装脚本：从当前 checkout 复制工具到 AGENT_LOOP_HOME/bin，**保留 goals**；原脚本误将非 Git 的非空 ~/.agent-loop 当克隆目标，实际不可用。
8. 新增只读 JSON 快照脚本：bin/agent-loop-status-json（AGENT_LOOP_HOME+ --goal/--all）。输出 local_filesystem_only、路径不等于可下载链接的标识、状态/轮次/是否终态/工件本机存在性/历史字段异常。用作其他 Agent 或 CX-PAN Hub Adapter 的最小只读输入，不调用网络/模型。
9. 新增 tests/test_contract.py（成功闭环、错误报告/决策、两轮流程、审批记录、哈希变化、目录校验、数字排序、安装隔离、JSON 出口）及 CI Job。完整验收以本轮实际执行回执为准。

## 3. 与旧现场记录的兼容性

本轮只读汇总的历史目录是 19 goals，其中 13 个非终态；这些数字并不意味着有 13 个进程正在执行。state.iteration=0 有 18 个记录；现存 23 份报告中有 22 份包含 11 个字段，部分 legacy 报告的 iteration 使用小数形式（如 1.1），部分 report_path 可能不对应实际文件。**新严格解析会拒绝这些非 v1.0 schema 的旧报告；本轮不修改旧记录、不批量迁移、不安装新版本到正在使用的 ~/.agent-loop/bin。**

按 goal 逐项完成历史数据协议审计后再选择：
- 历史任务保持原脚本可读、可审计；
- 对正在运行/未终态目标逐个明确文件身份、轮次、实际工件位置；
- 仅在需要续作时，明确指定从哪一轮开始、建立符合协议的新报告或独立 legacy adapter；不要为了通过新脚本而批量覆盖历史证据。

## 4. 未来可扩展架构：边界分层

- **Core agent-loop v1.x**：本地文件状态机 + CLI，只做协议验证、任务/报告/决策状态与只读 JSON 出口，继续维持不自动执行、不打开网络端口。
- **独立 CX-PAN Hub (可选外层)**：放在腾讯云，以 FastAPI + SQLite 记录跨 Agent 通信、工作单队列、idempotency_key、worker_run_id、ACL 和事件。Core goal_id ↔ CX-PAN task_id 必须显式映射、不能混为一谈。
- **本地/云端 Worker (可选 Adapter)**：经许可把 Hub 任务翻译成原生 Hermes/OpenClaw 任务调用，拉取任务、回传真实执行结果。不要用 HTTP 200 代替 Agent 执行验收。Core CLI 原有手动确认语义不能被 Adapter 悄悄跳过。
- **ChatGPT / Claude**：先复用已经连接的 CXRE 或 Claude Code 进程调用窄权限的 Hub CLI；后续考虑专用 Remote MCP。个人网页聊天不等于被外部可任意调用的运行时。
- **Funes / dots / Muse**：按真实可用的订阅、API、Worker 或 PULL_ONLY 入口接入。没有证据证明可自动唤醒的服务绝不声明全自动闭环。
- **Notion**：只写审核后成果和研究概述；SQLite 管瞬时任务状态，文件/对象存储管原文与工件。跨机文件地址需 signed URL 或授权传输及 SHA-256 验证，绝不能把 /home/xxx 或 D: 盘路径误当互联网 URL。

## 5. 立即可用的只读接口

从仓库检查所有 goal 状态，不启动任何 Agent：

~~~bash
cd ~/workspace/projects/agent-loop
python3 bin/agent-loop-status-json --all
python3 bin/agent-loop-status-json --goal my-project
~~~

只有真实部署并验证了 Worker/Hub 后才能宣称实现「ChatGPT ↔ Claude ↔ Hermes ↔ OpenClaw」全自动双向任务交接。

下一阶段目标：先完成 Core v1.1 独立回归、历史兼容性策略，再在独立 bridge/ 或 CX-PAN 仓库新增无副作用 Echo 任务 Hub；按真正返回 run_id、结果正文及幂等重复检查验收。

## 6. 本轮交付与验收指令

~~~bash
cd ~/workspace/projects/agent-loop
make validate
./scripts/validate-skills.sh
make contract-test
AGENT_LOOP_HOME="$(mktemp -d)" ./scripts/smoke-test.sh
git diff --check
~~~

以上只验证源码，不影响已安装的旧版 CLI。**状态：SOURCE_PATCHED / ISOLATED_TESTED / NOT_INSTALLED_TO_LIVE_HOME / CX_PAN_HUB_NOT_DEPLOYED**。


## 2026-10-26 增量：P1 Hub + Claude Code 已实机完成（后于上文旧状态）

早前本页中的「CX_PAN_HUB_NOT_DEPLOYED」是当时快照，不再代表最新状态。
已在现有 Git checkout 的独立 `bridge/` 目录实现 HTTP+SQLite 任务账本、受认证的 CLI、SSH 加密端口转发，以及 WSL2 上只读 Claude Code Worker。腾讯云 `cx-pan-hub.service`（loopback only）、本地 `cx-pan-ssh-tunnel.service` 与 `cx-pan-readonly-worker.service` 均已启用。

实机 P1 验证：
- ChatGPT CXRE 发 echo 请求 → 云端 SQLite QUEUED → 本地 Worker CLAIMED → COMPLETED，含 ECHO_OK 正文与 run_id。
- 同一 idempotency_key 重复提交命中同一个 task_id，云端只出现一次 QUEUED/CLAIMED/COMPLETED；不同正文重用同一 key 在隔离测试中返回 409。
- 两次 Claude Code v2.1.118 真正读取本地仓库，返回中文报告及 Claude session/run ID，其中第二次完全由常驻 Worker 自动领取，没有人工执行 Claude 命令。
- 人为停用本地 Worker → 提交任务保持 QUEUED → 重启**新**云端 Hub 后仍 QUEUED → 重启 Worker 后自动执行并返回 ECHO_OK。
- 16 项核心 + Hub 自动化回归测试全部 PASS。没有修改既有 19 个历史 goal，没有重启 Hermes/OpenClaw，也没有把 Hub 原生端口暴露到公网。

详见 [可选 Bridge 使用手册](../bridge/README.md)。最新状态：`CLOUD_HUB_ACTIVE / LOCAL_SSH_TUNNEL_ACTIVE / LOCAL_WORKER_ACTIVE / ECHO_E2E_PASS / CLAUDE_READONLY_E2E_PASS / QUEUED_RESTART_PASS`。限制：**不是**任意 ChatGPT/Claude 网页聊天之间互相远程唤醒；尚无独立 MCP/A2A 公网工具、未对接 Hermes/OpenClaw 任务执行、未实现 RUNNING 崩溃安全恢复。后续对这些能力单独验收。


## 2026-10-26 P2｜Hermes / OpenClaw 状态适配与任务心跳

**与 P1 的区别：** P1 验证了实际 Claude Code 只读分析任务的跨云/本地自动分派；P2 暂仅把 Hermes 与 OpenClaw 作为可查询的 `gateway.health` 目标，不冒充其大模型推理或命令执行已可自动委派。

运行环境：Hermes v0.22.5+1.g93cbf3e、OpenClaw 2026.10.5；两个既有 Gateway `systemctl --user is-active` 均返回 active。本地 Worker 使用白名单，不通过 Gateway token，不读取其私有对话或调用 shell；新 target `hermes.health.local`、`openclaw.health.local` 能由 ChatGPT→腾讯云 Hub→本地 Worker→云端回执。

**自动领单的实际回执（2026-10-26）：**
- Hermes health task_id `77bf380d-d4c8-4eaf-8ed5-7e885e34c45f`，最终 COMPLETED，返回 `gateway_state: active`、真实版本及 `model_invoked: false`。
- OpenClaw health task_id `eafac183-815f-45da-80f7-8d622ea87cf0`，最终 COMPLETED，返回 `gateway_state: active`、真实版本及 `model_invoked: false`。
- 原有 ChatGPT→Claude Code 能正常执行，P2 新增 Worker 在任务处于 RUNNING 时每约 20 秒向 Hub 发送受 attempt_id/worker_id 约束的 heartbeat。
- `GET /v1/tasks/{id}` 提供 `execution_health`：QUEUED 为 WAITING_FOR_WORKER；RUNNING 且最近 180 秒内有更新为 RUNNING_HEARTBEAT_OK；超过 180 秒未更新为 STALE_NEEDS_REVIEW；COMPLETED/FAILED 为 FINISHED。**不自动重做任何疑似中断的 RUNNING 任务**，以免重复式命令执行。Heartbeat 正常/伪造凭据失败/过期回报拒绝覆盖的隔离测试 PASS。

**暂时阻塞：** Hermes 工具受限的单轮模型请求遇到不支持 run-budget、safe-mode 需要显式模型、再到 invalid_params；OpenClaw 独立只读 headless agent exec 在配置 Node 24 与最小工具面后仍以进程退出码 137 结束。尚未查明 137 是否源自 OOM 或其他资源因素，因此不能宣称是某个特定模型/软件根因。没有改动其现有 Gateway、模型或 Provider 配置。不要把这两次失败当作网络 transport 故障；P2 health 场景与模型执行是两个不同 Gate。

**本轮额外负面回执：** P2 Claude 心跳验证 task_id `e79170d9-596b-4c6c-879c-ad1a7847f82f`，在 RUNNING 阶段至少两次实测得到 RUNNING_HEARTBEAT_OK；随后 Claude Code 返回进程 exit 1，任务最终 `FAILED`。旧 Worker 当时只记录退出码而没有抽取 JSON 中的错误 subtype，本轮已增加不泄露原始 stdout 的安全错误类别摘要；尚未用新版本复现 CLI 失败根因。故此任务只记心跳验收通过 / Claude 任务失败，不把它当作模型任务 PASS。

**下一阶段：** P3A 独立排障 Hermes 参数/API 调用及 OpenClaw `agent exec` 的资源/安全隔离，先做短小、可控、只读一轮；P3B 在双边模型 Gate PASS 后才接实际判断/审核任务；P3C 做受限制的远程 MCP 工具，让 Claude Chat 和 ChatGPT 分别真正从自己的对话窗口提交和读回，不再通过外层人工 CLI；P3D 提供按真实事件产生的 Notion 增量日志。

## P3 三阶段任务验收（2026-10-26）

核心层保持文件中继与显式授权；可选 bridge/workflow.py 已实机完成“固定仓库验证 → Hermes Gateway 状态 → OpenClaw Gateway 状态”三阶段自动领单、结果回传与同 ID 幂等复用。详细证据及模型级阻塞见 bridge/README.md；健康查询不等于模型执行。
