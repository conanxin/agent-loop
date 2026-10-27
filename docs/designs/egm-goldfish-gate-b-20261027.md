# EGM-R2｜Gate B1 上下文注入隔离 A/B 实机报告

> 测试日期：2026-10-27（北京时间）
> 状态：**B1_PASS / B2_PARTIAL / B3_NOT_RUN**
> 源仓库：`conanxin/agent-loop`，本报告为测试结果而非谷歌 EGM 官方插件兼容声明。
> Notion 研究主档：https://app.notion.com/p/40634a28189a81a4a14dc301f54e4af9

## 一、测量什么，没测量什么

本轮测试的可验证命题很窄：一个项目 `AGENTS.md` 中有无敏感信息的随机“环境词”；用户提示词中有独立的“来源词”。同一个模型分别在允许/禁止项目规则注入的模式下运行，检验是否能读到两个词。

- **正向对照**：允许项目规则注入 → 应能同时看到环境词和明确用户输入的来源词。
- **严格模式**：禁用规则注入 → 仍能看到来源词，但不得返回环境词。
- 两组使用相同的临时工作目录、相同的用户问题，唯一刻意变化为上下文注入策略。实际回答由脚本在原始 stdout 或 JSON 的 `final` 文本中比较词值。不会在 Git/Notion 发布随机原词，只有 SHA-256 摘要供原机核对。
- 这不是对所有记忆渠道、系统提示词、工具执行或语义审查质量的穷尽性证明。
- 原始随机词和输出仅在本机/腾讯云主机的 `~/.local/state/cx-pan/egm/` 中；生产配置与密钥未复制进工作区或 Git。

## 二、Hermes A/B（本地 WSL2）

环境：`DESKTOP-3A8N7VN`，Hermes v0.22.5，工作流 `egm-b-hermes-words-20261027`。

| 指标 | 对照组（普通 chat） | Goldfish（chat --ignore-rules） |
| --- | --- | --- |
| 用户输入来源词可见 | 是 | 是 |
| 仅在 AGENTS.md 的环境词可见 | **是** | **否** |
| 模型运行终态 | COMPLETED | COMPLETED |
| 时间 | 9.357s | 10.353s |
| 会话 ID | `local-6ab496da4a2a24df1fb358b98ec5a5734845b62d55f461cd5be0c102fcf30b23` | `local-9a36ee9968c64d28d21bbeddae7d651ef5d6341ea76eb2c2d2e613dd5004b997` |

本地回执 `~/.local/state/cx-pan/egm/egm-b-hermes-words-20261027/receipt.json`，终态 `PASS_CONTROLLED_AB`。普通模式与严格模式新会话 ID 不同。严格模式明确使用 `--ignore-rules --source tool -t clarify --in <临时目录>`，没有 `--resume`。

**重要代码级发现：** `hermes -z` 不显式传入 `AIAgent(skip_context_files=True, skip_memory=True)`；`hermes chat --ignore-rules` 则通过 `cli_agent_setup_mixin.py` 明确传入该两项标志。前者即使不恢复历史，也不能当作已经跳过项目文件/记忆。故本轮将独立 Goldfish 的默认测试入口由 `-z` 修订为 `chat -Q --ignore-rules`。该发现适用于本地实测版本，不推定未来版本不变。

最初尝试使用形似令牌的随机标记，Hermes 输出被自动脱敏成 `***`，无法判断实际读取情况，因此第一组被判 **INCONCLUSIVE**；第二组改成无敏感含义的随机词及 `SOURCE_WORD` / `AMBIENT_WORD` 字段，正反对照才有效。这是关于试验设计的重要教训。

## 三、腾讯云 OpenClaw A/B

环境：`VM-0-4-ubuntu`，OpenClaw 2026.10.3，工作流 `egm-b-cloud-context-v2-20261027`。

两组使用 `openclaw agent exec`、相同空白临时工作区、相同消息文件、MiniMax M3.1 Flash 和 pinned deny-all-tools 配置。对照配置与严格配置仅改变 `agents.defaults.contextInjection`（`always` vs `never`）；两个运行各自产生新会话 ID。

| 指标 | 对照（always） | Goldfish（never） |
| --- | --- | --- |
| 用户输入来源词可见 | 是 | 是 |
| 仅在 AGENTS.md 的环境词可见 | **是** | **否** |
| 模型运行终态 | COMPLETED | COMPLETED |
| 时间 | 24.499s | 20.931s |
| 会话 ID | `4ca0999c-1441-4c1e-8947-d9b9cb53e262` | `6c8a68ac-e927-4055-8321-21887baa948b` |

云端回执 `~/.local/state/cx-pan/egm/egm-b-cloud-context-v2-20261027/receipt.json`，终态 `PASS_CONTROLLED_AB`。严格组继续使用原有 `~/.openclaw/cxpan-p5-readonly.json5`，并确认 `tools.deny=["*"]`。用于正向对照的临时配置在运行完成后已自动删除，检查 `~/.openclaw/cxpan-egm-ab-*.json5` 残留数量为零。

首次云端试验因为尝试在临时目录的 `$include` 中引用 `~/.openclaw/openclaw.json`，被 OpenClaw 的配置目录边界检查拒绝，在模型执行前结束；这一轮的失败回执原样保留。第二次把对照配置临时建立在同一允许目录、执行完移除，才获得成功的 A/B。

**观测限制：** 本轮云端 `agent exec --json` 未返回可解析的 `toolSummary.calls`，记录值为 null；只能说静态配置禁止全部工具，不能谎称从模型执行轨迹独立量得了“0 次工具调用”。工具调用数量仍须另找执行追踪证据或专门采集。

官方关于上下文注入的解释：[OpenClaw contextInjection](https://docs.openclaw.ai/gateway/config-agents/workspace-and-bootstrap)；[OpenClaw agent exec](https://docs.openclaw.ai/cli/agent)；[Hermes CLI --ignore-rules](https://hermes-agent.nousresearch.com/docs/reference/cli-commands)。

## 四、在严格 Hermes 模式再次审查真实 SPEC 文档

在本地 Gate B1 A/B 通过后，将既有 `bridge/egm_local_probe.py` 修改为：

- 先从原有已完成 P6 来源任务取得 `docs/SPEC.md` 的原始封存胶囊；
- 检验原始字节摘要 `edb931dde0c56d88b73ded570fab18f2b81787ea9350948c9b3b118133893a72` 与胶囊的外层 SHA-256；
- 将按原行号完整标注的文件文字写入唯一临时 query 文件；
- 使用 `hermes chat -Q --ignore-rules --source tool -t clarify --in <独立目录> --query-file <文件>`（不传 `--resume`）；
- 保存真正返回的会话 ID、耗时、原文哈希、审查文本以及引用行号范围检查结论。

真实试验 `egm-r2-strict-20261027`：**COMPLETED**，97.51 秒，输入 8905 字符、输出 1376 字符，**15 处**结构有效路径/行号引用，Hermes 会话 ID `local-c6611373fa24f1ab5e33b6706818eddac266f5f1003f7dfebae8c099d19cc7c3`。

本地回执：`~/.local/state/cx-pan/egm/egm-r2-strict-20261027.json`。没有在这个新试验中再次调用云端模型，也没有覆盖前一轮的超时失败和 compact 成功回执。

这次严格模式指出三类可能改进：`make validate` 的只读性属于外部前提而非协议自身保证；绝对路径的机器字段与隐去用户家目录的示例写法应区分；`PASS`、`validation_result` 和 `DONE` 的机械验收条件需要补充。均仍需要结合其他规范与实际实现排除“只在 SPEC 单篇缺少描述”的误判。

## 五、本轮代码与离线验收

- `bridge/egm_isolation_ab.py`：Hermes 普通/严格模式合成 AGENTS 注入 A/B，对随机词只保存 SHA-256 摘要及本地原始记录。
- `bridge/egm_cloud_context_ab.py`：云端 OpenClaw `always`/ `never` A/B，对照临时配置不改生产配置，退出自动清理。
- `bridge/egm_local_probe.py`：将旧 `-z` Goldfish 调用更换为真正显式 `--ignore-rules` 路线。
- `tests/test_egm_gate_b.py`：5 项离线契约测试通过，检查启动标志、未带 `--resume`、`tools.deny` 未被替换、真实回执结构和来源行号。

## 六、裁定与下一阶段

**B1_PASS**：本地与云端的 AGENTS.md 合成规则注入正反对照均通过；两次严格模型运行均读到了合法来源词却没有返回环境词；真正的 `SPEC.md` 文档审查在严格 Hermes 入口再次成功。

**B2_PARTIAL**：新会话 ID、无 `--resume`、CLI 运行时显式记忆抑制标志以及云端 `contextInjection=never` 已有证据；但没有得到两宿主完整、可检索的系统提示词、所有记忆读取事件和工具调用详情，不能提升为 “所有上下文渠道零泄漏已证明”。

**B3_NOT_RUN**：三规格样本、普通审查与 EGM 审查的盲评、真实有效缺陷/误报/Token 成本比较尚未进行。根据 Google 官方 [Issue #61](https://github.com/google/elephant-goldfish-model/issues/61)，行业内相关 Benchmark 也仍需要严谨基线。

**后续建议**：只在内部继续改进角色绑定、来源证据和审查评分；不要开放公网 MCP 新权限、不要修改正常的 Gateway/Telegram 配置，不要把 P10 真人授权阶段覆盖为 EGM。
