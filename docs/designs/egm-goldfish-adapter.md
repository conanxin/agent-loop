# EGM-R2｜Goldfish 独立设计审查适配规格（草案）

> 日期：2026-10-27（北京时间）｜状态：DESIGN_ONLY + GATE_A_PARTIAL_PASS
> 仓库：conanxin/agent-loop｜设计目标：在现有 CX-PAN Hub 之上增加可选的、证据优先的独立设计审查流程。
> 来源研究： https://app.notion.com/p/40634a28189a81a4a14dc301f54e4af9
> 注意：CX-PAN 既有 P10 是网页客户端真实安装/授权阶段；EGM 不占用这个编号。

## 1. 问题与不可变边界

当前 P5 的 Claude → Hermes → OpenClaw 逐次评论会传递上一位审查员的结论，不符合 EGM 初次独立金鱼审查的输入隔离目标；P6 已有“同一原始胶囊 → Hermes / 云端 OpenClaw 并行”的基础。EGM-R2 以 P6 为起点，不重新建立独立 Hub、第二套 OAuth、第二套 Agent Bus。

必须维持：
- 原有 P7/P9 公网 MCP 的 safe-only 能力边界；新增 EGM 流程只经内部已认证 Hub 或明确授权的本地入口，**不新增公网任意模型/源码读取权限**。
- 不读取 NAS、其他磁盘和私人仓库；初期仅 `agent-loop` 显式白名单中的公开 UTF-8 规格文档。
- 保留现有 Gateway、systemd 服务、Telegram 路由，不为本试验重启生产服务。
- 保持人工架构决策权；自动完成的只是可核验的审查报告，不自动改实现代码。

## 2. 借鉴的 EGM 机制

- Elephant：持有业务上下文，创建规格和选择修订动作；生产角色可由 Claude Code / 本地 OpenClaw 实现。
- Goldfish A：只读、本地 Hermes，优先检查理解歧义、未定义术语、实施前提和验收条件。
- Goldfish B：只读、腾讯云 OpenClaw，优先检查架构风险、假设与失败场景。
- Synthesizer：在 A 和 B 都完成后才读取两份独立报告、去重、保留分歧。不得预先给 B 传 A 的结论。
- Owner：决定 ACCEPT、CONTEST、ESCALATE、DEFER；同意重要设计选择后才允许实施。

EGM 的官方 skill/persona 是方法学参考，**不是声称 Hermes/OpenClaw 原生支持 EGM 插件**。官方 [PR #119](https://github.com/google/elephant-goldfish-model/pull/119) 截至本设计尚未合并。

## 3. 当前源码能力（基线）

| 文件 | 已有机制 | 待增加 |
| --- | --- | --- |
| `bridge/evidence.py` | 三个明确 allowlist 文档、UTF-8、原始字节 SHA、行号与 18KB/650 行限制 | 后续显式加入一个样例设计文档（需同时修改 Hub 与 Worker 白名单） |
| `bridge/source_review.py` | 一次采集、同一 `parent_task_id` / 外层 digest 派发两审查者 | 专用 persona、项目规格的发现格式 |
| `bridge/hub.py` | 注册 target/capability、幂等键及 provenance 校验 | 只有确有必要时新增 internal-only `egm.*` target |
| `bridge/worker.py` | Hermes `-t clarify -z`，无文件/命令工具 | 确认真实新会话、禁用历史记忆注入及输入列表 |
| `bridge/cloud_worker.py` | OpenClaw pinned deny-all-tools 和 JSON 结果、sessionId | 确认真正新会话、角色专用提示词和会话轨迹 |
| `tests/` | P6 来源链回归 | 来源版本、分歧保留、隔离负向探测 |

注意：CLI 无工具权限不能推导出没有自动注入历史上下文。应把两者独立验证。

## 4. 最小真实试验（阶段 A，无服务改动）

输入：已放行的 `docs/SPEC.md`。使用 `bridge/source_review.py`（非新引擎），调用已经运行的 P6 证据接口，要求 Hermes 和腾讯云 OpenClaw 从头阅读相同文件并寻找两项隐含前提及一项缺失验收标准。

执行标识：`egm-r2-baseline-20261027`。
可检查的采集回执：原文 5299 bytes，`edb931dde0c56d88b73ded570fab18f2b81787ea9350948c9b3b118133893a72`。
同一原文封存结果 SHA：`cd569af9f6ecf36514493178444aae0b99cdc24b7efdb37d4927d96845be41b2`。

**2026-10-27 结果：** P6 Cloud 完成、P6 Hermes 在 95 秒时超时，随后 compact Hermes 使用同一原文封存胶囊完成 1414 字中文报告与 15 条路径行号引用；故标记部分通过。详细证据见 `egm-goldfish-baseline-20261027.md`。

**阶段 A 不声称通过：** 原生 EGM 独立角色实现、会话历史严格零泄漏、重要缺陷识别质量优于普通审查。需根据真实运行结果逐项验证。

## 5. 内部任务契约（阶段 B 提案，尚未实现）

```yaml
schema: cxpan.egm_review/0.1
workflow_id: "<stable-id>"
spec:
  repo_id: agent-loop
  path: docs/designs/egm-goldfish-adapter.md
  git_commit: "<git-commit>"
  source_sha256: "<64 lowercase hex>"
  capsule_result_sha256: "<64 lowercase hex>"
reviewers:
  - target: hermes.egm.local
    persona: comprehension
  - target: openclaw.egm.cloud
    persona: design_critic
execution:
  purpose: independent_design_review
  fresh_session_required: true
  inherited_parent_context: false
  tools_policy: read_only
output:
  raw_results: reviews/egm/<workflow-id>/
  consolidated: goldfish_review_report.md
```

这些字段是工程约束，不是已存在的 API。未经单独测试不得把这个草案发给生产 Hub 当成有效任务。

为了防止旧结果污染新文档，幂等键至少包含：（仓库/相对路径 + 文件 SHA + persona + rubric 版本 + 提示词版本 + 模型/运行配置版本）；只要变更其中影响判断的因素，就必须产生新版本的审查任务。

## 6. Goldfish 审查结果

每条结果需要：`finding_id`、`severity`（Blocker/Major/Nit）、`source_path`、`source_range`、`claim`、`evidence`、`why_it_matters`、`suggested_fix`、`confidence`。可以零发现，不允许捏造问题凑数。

- 验证 `source_range` 不越界；再由另一层检查**引文内容是否支持论点**，不能只校验行号。
- 汇总时保留两 Agent 不同观点及不确定项，不自动把 2 位模型的共识视为事实。
- 特别区分“当前代码与文档矛盾”和“未来计划的文件尚未存在”，后者不能作为已实现代码缺陷。

## 7. 验收 Gate

**Gate A：已放行源文并行实测**
- [ ] P6 捕获结果 COMPLETED、原文字节和两层 SHA 有回执。
- [ ] Hermes 与 Cloud OpenClaw 均返回 COMPLETED，`parent_task_id` 和 `source_sha256` 指向同一已完成采集任务。
- [ ] 双方原始回答存在有效路径+行号引文，明确标注角色/限制。
- [ ] 用相同输入再执行时只返回 duplicate，不发生二次付费模型调用。
- [ ] 保存经过人工判定的缺陷、误报及不能证明之处。

**Gate B：专用 EGM 运行接口**
- [ ] 隔离对照：Elephant 私密会话设只存在于历史的随机标记；Goldfish 的完整输入列表、注入文件和输出均受核查，无偷读历史的证据。
- [ ] 规范原文标记在合法输入中可正确读取；不同随机模型运行的 trace / run_id 有据可查。
- [ ] 执行服务注册新能力时保留原 P9 公网边界；现有系统不受影响。
- [ ] 使用至少三份不同复杂度规格进行普通 Review vs Goldfish 对照，人工打分，记录耗时与可获得的 token 花费。

如 Gate A 部分失败，不自动大范围修改 Hub 或 Worker。先记录实际失败原因，按最小差异修复。

## 8. 研究更新

每一次后续运行把日期、源 SHA、任务 ID、模型 run_id、结果文件、已核验和未核验结论追加到同一 Notion EGM 页面；技术规格与源码保存在 Git，Notion 用于人的决策与证据导航。
