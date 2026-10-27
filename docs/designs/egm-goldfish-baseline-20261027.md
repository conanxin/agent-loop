# EGM-R2｜同源双 Goldfish 实机基线与负面证据（2026-10-27）

**裁定：PARTIAL_PASS。** 同一份已封存的 `docs/SPEC.md` 已被腾讯云 OpenClaw 和本地 Hermes 分别用于审查，且两者均取得实质结果；但它们通过**不同提示词包装/执行路径**完成，尚未证明完全相同输入策略和会话历史隔离，更未完成官方 EGM 五阶段流程。首次原始 P6 Hermes 审查失败必须保留，不得覆盖。

## 1. 源文与任务回执

- 目标：`docs/SPEC.md`（176 行，5299 bytes）
- 原文字节 SHA-256：`edb931dde0c56d88b73ded570fab18f2b81787ea9350948c9b3b118133893a72`
- P6 封存结果 SHA-256：`cd569af9f6ecf36514493178444aae0b99cdc24b7efdb37d4927d96845be41b2`
- Source Hub task：`6a77fd07-0ee1-48ee-a9eb-9824409991b2`，COMPLETED
- 第一轮 P6 双审查：`egm-r2-baseline-20261027`

| Reviewer | 任务 ID / 工作流 | 真实终态 | 行号引文 |
| --- | --- | --- | --- |
| Hermes P6 原始全文 | `d5f2dbb5-6986-4c79-b2b6-d7237186da2f` | FAILED，固定 95s 模型调用超时 | 0 |
| Cloud OpenClaw P6 | `fce3fcbf-459b-4ef8-8774-0f26dc8040b3` | COMPLETED；5652 字符；run ID `openclaw:5ef71f99-d474-4618-86ef-06d5e4f51ec4` | 28 |
| Hermes compact | `egm-r2-compact-20261027` | COMPLETED；69.56 秒；1414 字符；输入 8905 字符 | 15 |

Hermes compact 运行 `bridge/egm_local_probe.py`，从同一 Source Hub task 取回完整已封存原文并重新验证双层哈希，直接通过本地 Hermes `-t clarify -z` 调用；原始输出与验收字段保存在 `~/.local/state/cx-pan/egm/egm-r2-compact-20261027.json`。再次用相同 workflow_id 调用返回 `REUSED_EXISTING`，未再调用模型。

补充诊断：Hermes 极短提示词独立返回 `EGM_HERMES_READY`，证明该 CLI / 模型至少能回应短请求；对第一轮长文本超时只能建立“与输入长度/生成时间相关的合理假设”，不能断言根因。

## 2. 双模型共同发现

1. **状态表时序模糊**：`SPEC.md` 中 `Next Action` 一列部分描述进入某状态的触发，部分描述该状态内部的操作，尤其 `HERMES_REPORT_WRITTEN` 与 `--report-path` 的前后关系。建议按 “源状态 → 目标状态 → 转移触发” 明示。
2. **决策 / 状态表缺交叉引用**：`SPEC.md` 中没有直接展示 `NEXT_COMMAND` / `REPAIR_COMMAND` 如何映射回 `OPENCLAW_PLANNING`，但仓库中 `docs/SCHEMAS.md` 第 127 行起、`docs/STATE_MACHINE.md` 第 86 行起确实有 `Decision→State Mapping`。正确表述是 **SPEC 本身不自足或缺少清晰引用**，并非整个项目没有映射。
3. **验收规则缺细化**：初读 `SPEC.md` 时，很难仅凭该文档确定 block 边界、缺字段、iteration 不一致、报告路径不一致时实现者和测试该如何处理。需对照真实 CLI 代码和其他规范，不应假定“没有实现验证”。

## 3. 审查结果中的校准点

- 云端报告宣称 `SPEC.md` 无 END 标记，该描述限于 SPEC 单篇成立；仓库 `docs/SCHEMAS.md` 已列出 `END_HERMES_COMMAND`、`END_HERMES_REPORT`、`END_OPENCLAW_DECISION`。如果报告把它当成**整个系统缺失**，则构成超范围推断。
- Hermes 报告指向状态映射缺失，同样应按 “本篇规格自洽性/导航链接” 处理，而非全仓库事实。
- 本次 28 与 15 是**行号范围检查通过的引用次数**，不是 28 与 15 个独立真问题；自动检验不保证每个论点的语义准确。
- 虽然源自同一个父证据胶囊，P6 Cloud 与 compact Hermes 输入包装不同，两个宿主是否注入个性化/历史记忆未知，不能标记“完全隔离 PASS”。

## 4. 本轮可复核改动和边界

新增文件（无需修改系统服务）：
- `docs/designs/egm-goldfish-adapter.md`：设计与 Gate A/B 目标。
- `bridge/egm_local_probe.py`：验证原文哈希、紧凑全行号输入、单次 Hermes 只读审查、失败/成功回执和重复工作流复用；不会调用 Cloud。
- `tests/test_egm_local_probe.py`：五项离线测试 PASS。

未做：修改 Hub target registry、Worker 对外权限、生产 Gateway、OAuth、Telegram、NAS 路径，未安装 Google EGM 插件，未证明 Goldfish 全历史隔离；没有收集完整 Token 使用量或对照实验。

## 5. 下一阶段 Gate B

- 显式创建全新隔离会话，记录 prompt/工具/注入文件清单；做“只有 Elephant 历史可见”的标记负向试验与“规格内标记”的正向试验。
- 使用**相同提示词与证据范围**对两模型开展独立审查，再设置普通 review 对照组，至少3份规格，每项分开计数真正有效缺陷/误报/耗时。
- 确认 EGM 内部目标与公网 P9 safe-only 协议分开，并经明确授权才扩展服务。
