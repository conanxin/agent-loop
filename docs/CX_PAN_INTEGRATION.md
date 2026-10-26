# agent-loop 原始目标复盘与 CX-PAN 接入边界（2026-10-26）

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
