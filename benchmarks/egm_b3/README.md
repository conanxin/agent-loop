# EGM-R2 Gate B3｜对照实验说明

本目录包含三份从 `conanxin/agent-loop` 实际规格抽取的**受控副本**，用于比较普通审查与 EGM Goldfish 风格审查。原生产规格未为本次实验而改动，样本冻结在 `08d7478` 提交的内容；后续设计文档追加进度不会改变测试输入。

## 设计

- `build_fixtures.py` 从 Git 提交 `08d7478ae11debd54c79474f81608336aede45aa` 中的 `docs/STATE_MACHINE.md`、`docs/SCHEMAS.md` 和 `docs/designs/egm-goldfish-adapter.md` 抽取片段，构成三个冻结样本。
- 每份样本加入两项**预登记的内部冲突**，另有一项成立的正常陈述作为误报观察点。具体内容、位置、源文件 SHA 放在 `ground_truth.json`。
- 三个审查样本保存在 `fixtures/`，`manifest.json` 锁定输入 SHA；`ground_truth.json` 不随模型推理脚本上传到腾讯云。
- 两种审查都使用 MiniMax M3.1 Flash、相同原文、相同输出字段；只改变审查提示方式。无外部工具、无历史对话，云端使用临时配置 `tools.deny=["*"]` + `tools.toolSearch=false` + `contextInjection=never`。
- 普通审查和 Goldfish 均运行于 fresh `agent exec`。本实验比较的是 **EGM 风格的结构化审查提示**，不是完整 EGM 的五阶段多 Agent 编排，也不是对 B1/B2 上下文隔离的重复测试。
- 原始模型输入、输出、JSON envelope、SQLite、Token 使用记录存腾讯云 `~/.local/state/cx-pan/egm/b3-20261027/`；仅把代码、冻结样本、评估规则和经核实的概括写入 Git/Notion。

## 两种运行条件

**原始条件**：`run_cloud.py` 六次调用，分组双并发、长篇审查 JSON、单次 125 秒预算。其结果是可靠性/交付路径实验，不能用超时项目直接计算质量差距。

**缩短条件**：`run_pilot.py` 和 `run_pilot_more.py`，三份样本分别进行普通审查与 Goldfish 风格审查，两次调用串行、限制最多两项发现、要求短 JSON。与原始条件的 prompt 不同，不能把两组条件混成同一个实验。

## 评分

`score.py` 读取第一轮结果并保守地标记失败、未验证的线号匹配。`recover_trace.py` 只用于区分“模型已生成但 CLI 未交付”和“模型根本没有完成”，不会把取证恢复结果提升为交付成功。

`score_pilot.py` 对短输出试验匹配预先登记的种子条款行号或同一个 finding 的证据引用。该自动结果叫 `PROVISIONAL_SEEDED_ANCHOR`，并不自动等于语义正确的真实缺陷。其它 findings 为待定，不应直接计为误报。任何最终质量判断都须由审查者检查问题是否真正解释了两条规范的冲突。

## 如何复用

在本地对冻结材料执行：

```bash
python3 benchmarks/egm_b3/build_fixtures.py
python3 -m unittest discover -s tests -p 'test_egm_b3.py' -q
```

模型实验涉及腾讯云已连接的私有状态，不在此处贴出云端账号或凭据；运行可参考 `run_cloud.py` / `run_pilot.py` / `run_pilot_more.py`。严禁盲目重复提交已经超时但状态不明的付费调用。

## 关键局限

1. 三个样本、六个预设冲突，均是“从真实文档摘录而来、经人为修改的测试副本”，不能称为未修改的真实生产缺陷集合。
2. 每个审查方式单次运行，无跨模型重复、无独立人类盲评，不具备显著性估计能力。
3. 种子冲突位于文档后部，可能较易发现，形成天花板效应。
4. Token 与 elapsed time 是该宿主实际观测，成本必须以返回的真实 cost 字段或账单为准，不能简单推断缓存和价格。
5. 只有当质量优势在更难的真实文档、不同模型和多次运行中稳定存在时，才考虑让 EGM 自动成为 CX-PAN 默认审查步骤；否则采用按复杂度触发的可选策略。
