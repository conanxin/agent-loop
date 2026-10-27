# EGM-R2 Gate B3｜设计审查有效性、交付可靠性与成本对照实验

研究日期：2026-10-27（北京时间）。裁定：**B3_PILOT_COMPLETED / NO_DEMONSTRATED_QUALITY_UPLIFT**。完整五阶段 EGM 与生产内部 Router 接入仍未实施。该结论只针对下面的 3 份种子样本、一个模型、每组一次运行。

## 一、为什么做这轮实验？

B1/B2 已在受控条件下核实了 Hermes 和腾讯云 OpenClaw 的项目规则注入、历史消息隔离，以及云端工具发现与禁止调用的边界。但“Goldfish 与作者上下文隔离”并不等于“Goldfish 审查必然发现更多正确问题”。

本轮比较的目标很明确：在模型、文档与输出约束保持一致的条件下，EGM 风格结构化审查是否比普通技术审查发现更多真实问题、减少误报，以及需要多少额外时间与 Token。

## 二、实验材料与事实来源

使用真实 `conanxin/agent-loop` 仓库在提交 `08d7478ae11debd54c79474f81608336aede45aa` 时的三份技术文档作为原始材料，只在**专用测试副本**中加入已登记的设计冲突，没有修改原生产规格：

| 案例 | 取材文件 | 种子问题 | 来源 / fixture |
| --- | --- | --- | --- |
| State Transitions | `docs/STATE_MACHINE.md` | 不合法的状态直跳、REPAIR_COMMAND 错误终态 | `state-transitions.md` |
| Schema Validation | `docs/SCHEMAS.md` | 必填审批字段被误改可选、report_path 被误改为相对路径 | `schema-validation.md` |
| EGM Integration | `docs/designs/egm-goldfish-adapter.md` | 首轮金鱼继承作者历史、无 SHA 仍称已验证来源 | `egm-integration.md` |

每份两项，共六项种子真问题，并含一条成立的普通规则作为误报观察。输入通过源 Git 提交与 `manifest.json` 中的 SHA-256 双重冻结；`ground_truth.json` 未复制到云端模型执行目录。真实原文的完整副本和答案可以在本仓库 `benchmarks/egm_b3/` 下检查。

**研究限制：** 这是“从真实规格中抽取片段并人为植入缺陷”的控制实验，不是 6 个自然发生的生产缺陷。问题集中在规范后部，容易形成检出率天花板。

## 三、审查者、运行环境与独立性

- 模型：腾讯云 OpenClaw 2026.10.3，`minimax/MiniMax-M3.1-Flash`，thinking=adaptive。
- 每一对普通审查和 Goldfish 使用相同的 frozen fixture、同一模型、新 `agent exec` 会话、相同 JSON 字段、最多两条问题；只改变审查方法提示词。
- 采用 B2 已验证的**临时**云端配置：`contextInjection=never`、`tools.deny=["*"]`、`tools.toolSearch=false`；全部有效实验中模型可见工具 schema=0，轨迹工具调用=0。未修改既有 P5 pinned 配置、Gateway、CX-PAN Hub 或公网 P9 MCP。
- 为减少先后顺序偏差，状态机 baseline→Goldfish；协议字段 Goldfish→baseline；EGM 接入 baseline→Goldfish。
- **这只是 EGM Goldfish 风格审查提示，非 Google 官方的独立多阶段并行审查、综合调度或全流程 EGM。**

## 四、第一轮：长输出、双并发、125 秒预算（失败但有价值）

使用 `run_cloud.py` 在三份样本上执行六次：结果 **0/6 正常交付可解析 JSON**。五次 TIMEOUT，另一次 FAILED_OR_UNPARSEABLE。不能拿它做普通 vs Goldfish 的质量比较。

为了区分“模型没有形成回答”和“CLI 未能将结果送回”，保留私有 `--state-dir`，通过 SQLite 的 `model.completed` 与 `trace.artifacts` 另做只读取证：

- 两份 **普通审查**虽未正常交付，但 trace 中已形成完整、可解析的 JSON，分别有 6 条 finding；在它们的引用与问题描述中可找到前两份样本的 4 个植入冲突。这两份只能叫 `TRACE_JSON_RECOVERED`，不能提升为 `COMPLETED`。
- 另一个 Goldfish 调用返回不合法的工具调用风格文字，无法解析为审查 JSON；不能把它当作真实工具操作或合规审查报告。
- 剩余三个运行没有可恢复的 model.completed 文字。
- 由于本轮同时改变了并发、输出长度和响应预算等因素，这个失败不能归因为“EGM 方法较差”。但它表明当前大模型运行与 CLI 交付链路在较长审查任务上存在可靠性问题，应首先确保稳定交付。

失败工件和恢复文本存于腾讯云私有 `~/.local/state/cx-pan/egm/b3-20261027/runs/`，本地评分副本位于 `~/.local/state/cx-pan/egm/b3-results-20261027/`，没有上传原始对话到 Notion。

## 五、第二轮：缩短 JSON 输出、串行审查（成功）

使用 `run_pilot.py` 和 `run_pilot_more.py`，每份规格的两个审查方式改为串行运行，提示词要求最多两条最重要的冲突、尽量简短。结果 **6/6 正常交付、可解析，实际调用工具均为 0**。

### 5.1 质量——12 条报告经过证据复核

| 案例 | 普通审查识别的种子问题 | Goldfish 识别的种子问题 | 额外有效问题 |
| --- | ---: | ---: | ---: |
| State Transitions | 2 / 2 | 2 / 2 | 0 |
| Schema Validation | 2 / 2 | 2 / 2 | 0 |
| EGM Integration | 2 / 2 | 2 / 2 | 0 |
| **合计** | **6 / 6** | **6 / 6** | **0** |

模型返回 12 条 finding。根据 `adjudication.json` 中逐条核对的冲突解释与原文引用，**12 条均准确说明对应的植入问题**，此受控范围没有确定误报。两种方法在种子真问题检出率上都是 100%。

**注意**：这是由 ChatGPT 助手复核、知道测试真值的证据审查，**不是独立人类盲评**，也没有对真实自然缺陷的全量负例进行系统标注；因此不能将“0 个确定误报”当成两个模式在实际生产里的假阳性率为 0。

### 5.2 时间、Token 和可用性

| 案例 | 普通审查耗时 | Goldfish 耗时 | 普通审查总 tokens | Goldfish 总 tokens |
| --- | ---: | ---: | ---: | ---: |
| State Transitions | 34.626 秒 | 33.106 秒 | 3,701 | 4,933 |
| Schema Validation | 23.043 秒 | 25.144 秒 | 3,691 | 3,777 |
| EGM Integration | 27.774 秒 | 45.826 秒 | 4,620 | 4,214 |
| **三组合计** | **85.443 秒** | **104.076 秒** | **12,012** | **12,924** |

Goldfish 在三组里**没有增加检出的问题数**，但合计多花 **18.633 秒（+21.81%）**、多 **912 tokens（+7.59%）**。在第一组它略快，第三组更慢；单次样本的变动较大，这些差异不足以推出显著的性能趋势。

Token 是 OpenClaw `trace.artifacts.usage` 实际记录的模型用量，不代表已经取得准确美元账单；不能把缓存、思考 Token 与供应商定价直接混成一个确定费用。**本阶段未确认真实 USD 花费**。

第一轮交付率 0/6、第二轮交付率 6/6，只能说明“在本次环境中，较短的串行任务交付稳定得多”；本实验未隔离并发与输出限制这两个因素，不能单独判断哪个造成改善。

## 六、这对现有 CX-PAN 的具体决策意味着什么？

1. **不应全面默认启用 EGM。** 对普通文档分析、简单修复和明确的小规模任务，仍优先一个有能力的 Agent 完成工作；在本轮简单种子矛盾中，Goldfish 并未比普通审查多发现缺陷。
2. **保留 Goldfish 隔离能力作为可选质量关卡。** 当任务跨机器、涉及架构变更、长时间对话积累了大量假设、多个 Agent 互相引用同一结论时，EGM 的冷读独立审查具备合理的防偏见价值，但这是风险控制价值的机制判断，当前没有量化收益证明。
3. **先统一单次执行质量。** 需要固定输出长度、数据来源 SHA、单轮时限、合法 JSON 解析与 CLI 正常交付；超时后的 trace 恢复不得误记为完成。用可观察的真实工件与来源链而非 Agent 自称成功来验收。
4. **暂不注册正式内部新 target。** 最多先把 Goldfish 方法封装为人工按需调用的私有脚本；不得使 P9 公网 MCP 获得付费模型、NAS、Shell 或任意本地文件权限。
5. **更高质量实验应先换成困难/真实任务。** 下一轮选择真实、未经人工插错的 3–5 个有独立权威参考的设计问题，或用人类专家设计不易被关键字命中的隐含约束，再由不知分组的审查者对问题有效性、引用支持、误报和成本做独立复核。需多次运行与至少两个模型，才考虑自动化升级。

## 七、工程成果、可复现性与保存边界

本轮实现：
- `benchmarks/egm_b3/build_fixtures.py`：冻结 3 份源自真实规格的测试文件并记录完整来源摘要。
- `benchmarks/egm_b3/fixtures/`、`manifest.json`、`ground_truth.json`：样本与预登记种子真值。
- `run_cloud.py`：第一轮长输出并发实验；`recover_trace.py`：将模型已生成但 CLI 没交付的工件归类为取证恢复。
- `run_pilot.py`、`run_pilot_more.py`：缩短输出的串行三组配对实验；脚本在云端使用一次性只读配置。
- `score.py` 与 `score_pilot.py`：自动检测种子位置候选，**不将行号匹配等同真实语义正确**。
- `adjudication.json`：12 条发现的逐项证据复核（非独立人类盲评）。
- `generate_results.py`、`results_summary.json`：从原始受限执行回执生成可检查的聚合指标。
- `tests/test_egm_b3.py`：冻结输入、真值隔离和评分逻辑的离线测试。

云端运行原件仍在 `/home/ubuntu/.local/state/cx-pan/egm/b3-20261027/`；本地结果副本位于 `/home/conanxin/.local/state/cx-pan/egm/`，并未将全部模型原始 output、Provider 配置或私有数据提交到公共代码库。

**阶段裁定：B3_PILOT_COMPLETED；质量提升尚未证实，建议继续以单 Agent 为日常默认、独立 Goldfish 为复杂任务可选审查。**
