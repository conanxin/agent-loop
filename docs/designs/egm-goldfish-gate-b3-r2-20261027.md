# EGM-R2 Gate B3-R2｜未植入缺陷的真实源码独立审查：部分完成与可靠性门禁

研究日期：2026-10-27（北京时间）。**阶段裁定：PARTIAL / QUALITY_UPLIFT_INCONCLUSIVE / DO_NOT_AUTO_DEPLOY**。

这是前一轮 B3“3 份测试副本各植入 2 处显式矛盾、普通审查与 Goldfish 均 6/6”的后续研究。重点是用未经植入错误的真实代码判断 Goldfish 是否多找到有证据的实质问题。本阶段已冻结资料、实施两组正式源码审查条件、完成首次独立匿名证据复核；但**由于多次超时，尚未取得足以推导质量增益的配对样本**。

## 1. 三组原始材料，未对源码植入错误

Git 来源固定为 `231290845a4117ba7e05ac5226b802b4faf11045`，从原提交按路径与行号抽取片段，所有源文件 SHA 与审查包 SHA 均可核验。

| 领域 | 真实文件范围 | 审查目标 |
| --- | --- | --- |
| 状态机与 CLI | `docs/STATE_MACHINE.md`、`docs/SPEC.md`、`bin/agent-loop-relay`、`bin/agent-loop-set-state` | 转移规则与运行实现是否矛盾；人工改写是不是非预期绕过 |
| P6 证据链 | `bridge/evidence.py`、`bridge/source_review.py`、`bridge/hub.py`、`bridge/cloud_worker.py` | SHA、父子任务、审查来源和错误恢复 |
| P9 MCP 权限 | `bridge/mcp_gateway.py`、`bridge/oauth_store.py`、`bridge/oauth_server.py` | 公网安全能力白名单与 OAuth 范围边界 |

审查包：`benchmarks/egm_b3_r2/packets/`（较全片段）与 `compact_packets/`（定向短片段）。独立的 `manifest.json` 与 `manifest_compact.json` 固定路径、行号、SHA。**精简审查包是片段，不是整个仓库。** 模型若以缺少某处代码证明“整个系统没实现”，应判证据不足。

## 2. 三种运行条件必须分开

所有真实调用使用腾讯云 OpenClaw `agent exec`、MiniMax M3.1 Flash，同一个模型/一份输入范围内普通与 Goldfish 风格提示词对照；`contextInjection=never`、`tools.deny=["*"]`、`tools.toolSearch=false`，每次是独立的新会话与私有临时 state-dir。原始生产配置不变。

| 条件 | 已实际尝试 | 正常交付 | 失败类型 |
| --- | ---: | ---: | --- |
| 完整定向源码，adaptive | 2 | 1 | Goldfish 超时 140 秒 |
| 紧凑源码，错误设置 low thinking | 2 | 0 | 两次均因 MiniMax M3.1 不支持 low（仅支持 adaptive / ultra），模型审查未进行 |
| 紧凑源码，adaptive | **6** | **2** | P6 与 P9 的普通、Goldfish 各超时一次，合计四次 135 秒超时 |

这里总共十个实验工作单，来自**三种不同条件**，不能统计一个混合的“EGM 成功率”。且紧凑 adaptive 方案原计划 12 个位置：仅执行第一轮 6 个（每个案例普通与 Goldfish 各一次），第二轮 6 个因交付可靠性未达标而**没有尝试**，绝不能把未运行当成失败模型输出。

第一种条件中普通审查虽然正常返回、提供两条候选问题（91.402 秒、12,222 记录 tokens），Goldfish 超时，不构成完整配对。

第二种条件中两次失败是**参数兼容错误**，并非模型审查质量失败；保留旧回执而另开第三种条件，绝不覆盖原有工作单。

## 3. 紧凑 adaptive 条件的真实结果

| 案例 | 普通审查 | Goldfish | 能否评分质量差距 |
| --- | --- | --- | --- |
| 状态机 | COMPLETED；71.395 秒；10,545 tokens；2 条候选 | COMPLETED；62.866 秒；8,519 tokens；2 条候选 | 仅此一组成功配对，且候选意见需要复核 |
| P6 | TIMEOUT，135 秒 | TIMEOUT，135 秒 | 不能 |
| P9 | TIMEOUT，135 秒 | TIMEOUT，135 秒 | 不能 |

对成功交付的两项，执行轨迹显示模型可见工具数量 0、工具调用数量 0、先前对话消息数量 0；source SHA 与原始行号均属于冻结代码包。普通审查 9 次文件行号引用、Goldfish 6 次，均通过**范围**校验，但不能把这些引用计作 9 个或 6 个真正的安全问题。

针对 P6/P9 的四次超时，还专门只读检查了私有 SQLite：四次都没有 `model.completed` 事件；不能恢复有效审查回答，不能算成“模型检查后未发现问题”。这个结果也不足以判定超时发生于推理、模型路由、会话初始化或网络的哪个环节。

## 4. 匿名独立模型评议（Hermes）

把第一组**四个候选发现**匿名打乱，移除普通审查与 Goldfish 标签，附相应真实源码路径与邻近行，通过新的 `hermes chat -Q --ignore-rules --source tool -t clarify` 会话执行，回答经过合法 JSON 检查。Hermes 独立评审耗时 103.51 秒。

- 四个 finding **均被评为 PARTIAL**，没有一个独立确认的 SUPPORTED 真实缺陷。
- 四条意见归并为**两类根本机制**，两种审查策略都提出了两类：
  1. `agent-loop-set-state` 对合法目标状态进行写入，却未在这段代码中强制合法转移边。**代码行为可观察，但 CLI 也可能是有意提供的人工恢复/手工 override 工具**。缺少被授权调用者、安全边界与真实业务约束，不能直接断言有越权漏洞。
  2. `agent-loop-relay --decision-path` 可从 `HERMES_REPORT_WRITTEN` 阶段接收决策，文档转换表常以 `OPENCLAW_JUDGING` 为决策前置状态。**现象存在，但报错和入口代码暗示双态支持可能是有意兼容路径**，尚需更多外部实现与正常操作流程才能判断是不是 Bug。
- 第二位模型仅作独立**模型**盲审，**不是独立人类专家盲评**；其 PARTIAL 裁定同样应保留不确定性。
- 无论普通审查还是 Goldfish，暂时都没有在此成功配对中形成“经独立支持的额外发现”。这不等于证明系统无漏洞，也不等于证明 Goldfish 在真正复杂问题上永远无益。

私有原始复核数据：`~/.local/state/cx-pan/egm/b3r2-blind-preliminary-v2/`；面向 Git 与 Notion 的汇总：`benchmarks/egm_b3_r2/results_summary.json`，不上传本地可能敏感的临时执行数据库。

## 5. 方法论得失与下阶段优先事项

**有价值的真实结论**不是性能胜负，而是应建立“质量审查之前先过执行交付门禁”。

1. 真实跨文件审查的执行稳定性明显不足；目前不能用一次成功状态机配对外推整个跨主机 Agent 安全审查领域的优势。
2. 在状态机的单组成功配对中，普通审查与 Goldfish 发现了相同两类风险，但两者均需要更多证据；没有增量可确认缺陷。
3. 下一轮优先为运行路径建立可靠的模型/超时/输出监控，并在已验证能读取大段源码的模型与配置上重测；不得用新提示词偷偷覆盖旧结果，不能在失败或可能仍在运行时无上限自动重试。
4. 真正的 EGM 项目价值需要在设计规格、真实源码、权限边界之间有完整足够的证据；只给部分摘录产生的缺陷指控应采取保守审查。
5. 不应现在为 CX-PAN 增设 EGM 自动常驻 target 或扩大公网 MCP 权限。普通日常任务继续由单 Agent 负责；跨主机/安全重要方案可选择手工触发的独立 Goldfish，并保留人工裁决。

## 6. 工程交付与原始证据位置

源码与协议：
- `benchmarks/egm_b3_r2/build_packets.py` / `build_compact.py`：从固定提交冻结未修改代码。
- `run_cloud.py` / `run_compact.py` / `run_compact_adaptive.py`：分离不同实验条件及每次唯一执行状态；不会盲目重跑同一个异常任务。
- `score_delivery.py`：实际交付、来源引用、耗时、tokens 和未尝试的工作单分开统计。
- `prepare_blind.py`：在第二模型审查前隐藏策略标签、乱序输出并构建文件/行号证据窗口。
- `summarize.py` / `results_summary.json`：从受限私有回执输出可以公开的匿名统计和裁定。
- `PROTOCOL.md` / `README.md` 与 `tests/test_egm_b3_r2.py`：预先登记评分门槛、来源不变性与执行安全测试。

真实云端工件保存在腾讯云 `~/.local/state/cx-pan/egm/b3r2-20261027/`；本地结果副本在 `~/.local/state/cx-pan/egm/b3r2-20261027-results/`；匿名第二模型原文在 `~/.local/state/cx-pan/egm/b3r2-blind-preliminary-v2/`。Git 和 Notion 不保存私有密钥或真实会话数据库。

**阶段状态：B3_R2_PARTIAL，质量差距暂不可判定；首先需要通过真实长文审查的执行稳定性门禁。**
