# EGM-R2 Gate B3-R3｜长源码审查：模型执行兼容性与交付稳定性复核

> 北京时间：2026-10-27
> 阶段裁定：**B3_R3_SCOPED_EXECUTION_PASS / GENERAL_RELIABILITY_NOT_PROVEN**。
> 本轮 Git 实验基线：`e825140caa2929ff6d338afb3c77ea657c3a627b`。
> 没有安装 Google EGM 官方插件、没有修改生产 Gateway/Worker、公网 MCP、OAuth、NAS 或默认模型。

## 1. 回到原始失败：不能把四次超时称为“0 个问题”

此前 B3-R2 使用单独新会话的腾讯云 OpenClaw 2026.10.3、`minimax/MiniMax-M3.1-Flash`、`adaptive`：

| 被审查的冻结源文 | 已标注提示词大致规模 | 普通审查 | Goldfish |
| --- | ---: | --- | --- |
| 状态机 / CLI | 12.4k 字符 | 71.395 秒完成 | 62.866 秒完成 |
| P6 证据链 | 15.5k 字符 | 135 秒超时 | 135 秒超时 |
| P9 MCP/OAuth | 16.9k 字符 | 135 秒超时 | 135 秒超时 |

本轮重新只读检查了这六次保留的 SQLite。四次超时都已经创建会话，并留下 `transcript_events=5`、一个 `session_windows` 记录，**但 `trajectory_runtime_events=0`、没有 `model.completed`**。成功的两次各有 7 个轨迹事件。不能据此断定网络请求绝对未发出，只能判定在这条记录路径里没有收到可用的模型完成事件。

排除了一些简单误诊：当前腾讯云主机仍有约 3.8 GB 可用内存，两个云端 CX-PAN 服务 active、NRestarts=0，实验后无残留 `agent exec`。但这些指标不证明模型 Provider 完全正常，也不证明“超过 15k 字符一定失败”。

## 2. 模型清单与参数兼容性不是一回事

安装版 OpenClaw 的 `models list --json` 报告 4 个已发布/配置的候选：`minimax/MiniMax-M3.1-Flash`、`minimax/MiniMax-M2.7`、`minimax/MiniMax-M3`、`zai/glm-5.3`。提供者发现提示“部分刷新未成功”，因此目录的 `available=true` 不能视为实时请求已经成功。

首次把备用 M2.7 直接套用 Flash 的 `--thinking adaptive`：**14.138 秒后被明确拒绝**，错误消息列出 M2.7 接受 `off / minimal / low / medium / high / ultra`，不接受 `adaptive`。该任务未进入成功模型推理流程，失败回执照原样保留。

改为对 M2.7 指定 `--thinking medium`，并保持只读工具策略、上下文注入关闭，模型实际运行成功。为防止未来重复浪费模型调用，`benchmarks/egm_b3_r3/probe_model.py` 在提交前检查**模型与思考级别的兼容组合**，对没有验证过的模式不自动猜测可用。

## 3. 同一来源、同一精简提示词的跨配置对照

P6 来源是 Git 提交 `e825140` 已冻结的 `p6-evidence-integrity` 片段。跨配置短答对照不仅原文 SHA 相同，**完整 prompt SHA-256 也完全一致**。更改的是模型和它各自接受的 thinking 设置：

| 运行配置 | 输入 | 运行结果 | 实际耗时 | 模型完成事件 |
| --- | ---: | --- | ---: | --- |
| MiniMax M2.7 + medium | 15,221 字符 | COMPLETED | **24.365 秒** | 是 |
| MiniMax M3.1 Flash + adaptive | 15,221 字符 | TIMEOUT_NO_MODEL_COMPLETE | **115.095 秒** | 否 |

M2.7 那次 `trace.artifacts.usage` 实测 input=5826、output=271、total=6225 tokens，model-visible tools=0、tool.call=0，实际路由确认为 MiniMax-M2.7。Flash 那次按时间限制停止，不能从没有模型完成事件推断实际成本为零。

**边界：** 每种模型配置只跑一次；M2.7 与 Flash 的 thinking 级别不同，不能声称这是隔离了所有变量的“纯模型 A/B”、统计显著的胜负或原 Flash 服务整体故障。这个结果仅支持将 M2.7 + medium 视为本环境近期的**备用受控运行档**。

## 4. P9 第二个独立源文也成功

相同的 M2.7 + medium 模式运行 P9 真实的受限 MCP/OAuth 源码快照，短回复诊断：

- `p9-public-mcp-boundary`：16,584 字符，**24.809 秒完成**；
- input=6229、output=862、total=6723 tokens；
- `model.completed=true`、无工具 schema、无工具调用。

因此已有来自 P6、P9 两个不同审查域的成功运行，而不只是重复调用同一短提示。这仍不是长任务的可靠性服务等级测试。

## 5. 有实际审查内容的两个完整 JSON 回执（不仅是 Smoke）

为避免“模型能回应一句话”被错误视作“已能可靠审查源码”，另用 `bounded_review.py` 对 **完整冻结片段**进行真实结构化审查，每次最多两条主张、必须提供原文件路径和行号、独立 session、没有外部工具：

| 领域 | 源文提示词字符 | 真正交付 | 耗时 | total tokens | 模型发现 |
| --- | ---: | --- | ---: | ---: | ---: |
| P6 证据链 | 15,387 | COMPLETED | **38.881 秒** | 8,143 | 1 项 |
| P9 公网 MCP/OAuth | 16,750 | COMPLETED | **32.433 秒** | 7,219 | 1 项 |

这两份符合严格 JSON 输出、成功从 CLI 返回、具有真实 `model.completed`，所有模型可见工具/实际工具调用仍是 0。所有引用通过原文件路径与行号**结构性**校验，但结构性校验不能替代真实性评审。

在这组小规模观察中，M2.7 + medium 的短回复诊断 2/2 成功、结构化审查 2/2 成功，合计 **4/4 个不同任务回执完成**。这不能预测该组合长期成功概率；当前也没有确认真实美元计费。

## 6. P6 发现：已用独立临时输入复现的生产者/验证者限制不一致

P6 审查报告指出：`bridge/evidence.py` 的 `capture()` 只对源文件原始字节设 `MAX_BYTES=18000`，但 `verify()` 先限制序列化 JSON 原文不超过 **40,000 字节**。对于允许的非 NUL 控制字节，`json.dumps` 会进行转义，可能出现大幅膨胀。

只在 `TemporaryDirectory` 下构造允许相对路径 `docs/SPEC.md`，写入 10,000 个 UTF-8 允许的 U+0001 单字节控制符：

- `capture()` 成功；
- 返回的 JSON 证据胶囊为 **60,194 字节**；
- `verify()` 拒绝：`invalid capsule type/length`。

因此 **`capture` 可生成 `verify` 不接受的胶囊**这个不变量缺口已复现。现有 P7 对外仅提供固定三份真实公开文档；没有证据说明它们包含类似控制字节，更不能直接称之为公网安全漏洞。

**候选最小修复（未生产部署）**：在 `capture()` 完成规范 JSON 序列化后同步应用原 `verify()` 的 40k 原文上限，提前以明确的输入限制错误拒绝不兼容证据；或全面评估后修改验证器与 Hub 的一致预算，先增加单元测试及 P6 路径回归再变更。不可简单调大 Hub/Worker 字节预算且遗漏上游配额、安全负载边界。

## 7. P9 发现：配额先占用后提交的行为确实存在，但需要纠正模型表述

P9 短答报告最初称任务创建失败后无法用相同幂等键重试，这是**过度推断**。源码 `bridge/mcp_gateway.py` 的 `task_submit_safe` 先调用 `quota_slot` 再调用上游 `mcp_rpc`，确实存在“请求尚未成功、唯一当日配额项已提交”的顺序问题；但同一键命中 `quota_slot` 的既有记录后可正常返回，再次运行上游 `mcp_rpc`。这里不存在已证明的“相同键永久不可重试”。

独立的临时 SQLite 复核（完全不碰真实配额库）验证：
- 失败的上游阶段模拟后仍有 1 项配额记录；
- 同一键再次调用 `quota_slot`，配额仍是 1 项；
- 换新的唯一键调用，变成 2 项。

因此准确结论是：**每天的唯一请求配额按尝试的唯一键预留，失败的首次提交也可能占一个槽，但重试同一键不再额外占槽**。这是否符合用户承诺的“每日新任务数”、是否本来就是反滥用设计，需由服务所有者明确。若决定改变，不能因为上游超时就盲目退回配额：远端任务可能已经创建但响应丢失，应先与真实幂等任务记录和最终状态对账。这不构成目前已确认的越权漏洞。

## 8. 可实施的 B3-R3 执行门禁（仅实验路径实现）

建议模型调用之前执行以下顺序：

1. **模型/思考兼容**：在允许的模型配置清单内选择；把明确支持的 `MiniMax-M2.7 + medium` 当作待检验的备选运行档；不可套用 Flash 的 `adaptive`。
2. **唯一输入与幂等性**：记录真实源码提交与源 SHA、prompt SHA、模型和 thinking，旧任务存在或尚未最终确定时禁止新一轮付费调用。
3. **隔离且真正无工具**：显式 `contextInjection=never`、`tools.deny=["*"]`、`tools.toolSearch=false`，固定私有 `--state-dir`；不要扩大公网 P9 OAuth/MCP 权限。
4. **分离终态**：模型完成事件、JSON 成功返回与来源语义审查分别验收；TIMEOUT/FAILED 不能推导零问题，也不能将无法解析的输出当作合格报告。
5. **有上限的付费调用**：单次超时受控，失败保留；对失败工作单先读取状态与轨迹，不自动无限重试或多模型 cascade。
6. **修复前审查**：P6 捕获长度不变量由独立回归验证；P9 配额语义属于风险与需求决策，确认目标行为后再变更生产系统。

**当前选择：** 暂不修改云端 Agent 的全局默认模型、不注册 EGM 常驻付费 target，不部署 P6/P9 修复补丁。该阶段只创建可复核的诊断、限定调用工具与研究记录。

## 9. 工程文件和回执边界

实验代码：`benchmarks/egm_b3_r3/probe_model.py`（模型与 thinking preflight、任务唯一性、证据 SHA、轨迹状态）、`bounded_review.py`（真实结构化短 JSON 审查）、`diagnose_invariants.py`（临时安全环境复现）、`summarize.py`（读取私有真实回执并生成净化结果）、`results_summary.json` 与 `invariants_summary.json`。针对性单元测试在 `tests/test_egm_b3_r3.py`、`tests/test_egm_b3_r3_bounded.py`。

腾讯云实际请求原始回执仍存 `~/.local/state/cx-pan/egm/egm-b3r3-*/`；本地净化处理副本在 `~/.local/state/cx-pan/egm/b3r3-receipts-20261027/`。不把用户凭据、完整模型原始回复、临时配置和 SQLite 复制到公开 Git 或 Notion。

**下一阶段建议：** 采用 M2.7 + medium 对另外一份更难的源码包做有限重复验收；在稳定交付后才重启 B3-R2 的严格质量评估。维护固定 SHA 与人工复核，不能把这次 4/4 小样本成功误当生产 SLA。
