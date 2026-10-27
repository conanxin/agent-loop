# EGM Gate B3-R3｜模型参数与长文审查执行门禁

本阶段目标不是宣布 Google EGM 的质量胜出，而是解决 CX-PAN 既有 B3-R2 对较长真实代码片段调用时出现的“模型未完成、长时间超时”问题。

## 权威范围

- 冻结输入：`benchmarks/egm_b3_r2/manifest_compact.json`，来自 Git commit `e825140caa2929ff6d338afb3c77ea657c3a627b`，仅三类公开自有源文件片段。
- 本阶段实际验证范围：P6、P9 两种输入，二者提示词均约 15–17k 字符。
- 云端 OpenClaw 2026.10.3：`agent exec`，新会话、受限工作目录、零模型可见工具、零工具调用。
- **本项目代码是只读私有研究实验，未进入生产 Hub/Worker，且不对公网 MCP 赋予任何新能力。**
- Notion 主档：https://app.notion.com/p/40634a28189a81a4a14dc301f54e4af9

## 本目录文件

| 文件 | 用途 |
| --- | --- |
| `probe_model.py` | 模型、thinking 兼容前置校验；对同一个源码提交/提示词进行 bounded smoke test，避免重复发出昂贵请求 |
| `bounded_review.py` | 用已验证的 M2.7 + medium 执行实际短 JSON Goldfish 只读代码审查，严格解析结果、核对引用行号 |
| `diagnose_invariants.py` | 使用 `TemporaryDirectory` 和临时 SQLite 独立复现 P6 胶囊长度不一致，以及 P9 配额预留/同键重试语义 |
| `summarize.py` | 从非公开运行回执生成净化结果，验证 P6 配对 prompt SHA 完全一致、确认实际模型/模型完成事件与零工具调用 |
| `results_summary.json` | 6 个不相混淆的模型诊断/结构化审查工作单；记录模型配置、SHA、终态、时间、Token |
| `invariants_summary.json` | P6/P9 的临时环境代码事实复现，不包含真实用户数据 |

完整分析、限制和结论参见 `docs/designs/egm-goldfish-gate-b3-r3-20261027.md`。

## 核心实验结论

- 对于同一份 P6 精简 prompt，MiniMax-M2.7 + medium 完成，MiniMax-M3.1-Flash + adaptive 超时 115 秒，没有完成事件。只测试一次，**模型与 thinking 同时变化，不能推断全局稳定性或归咎提供者**。
- M2.7 + medium 对 P6/P9 的两个短回复诊断、两个完整证据包短 JSON 审查，均成功交付且零工具调用。模型使用量由原始 OpenClaw trace 而不是估算提供。
- 未经授权，不应自动切换所有生产 Agent 默认模型，更不能将“完成”直接当作“发现具有语义正确性”。
- P6 的证据胶囊序列化长度问题由临时合法输入复现；P9 的配额预留行为存在，但同幂等键仍可重试，是否改变按业务与抗滥用策略决定。

## 核查、不重复付费

- 测试入口：`python3 -m unittest discover -s tests -p 'test_egm_b3_r3*.py' -q`（所有模型调用已 mock，不产生付费请求）。
- 本地代码事实复核：`python3 benchmarks/egm_b3_r3/diagnose_invariants.py --output benchmarks/egm_b3_r3/invariants_summary.json`（只写临时文件与结果工件，不访问生产 Hub）。
- 私有回执属于用户自己的云端机器 `~/.local/state/cx-pan/egm/`；本地读取它们时只保留有效的 model/trace/费用字段，**不会把原始敏感配置、密钥、完整提示词或会话数据库上传 Git**。
- `probe_model.py` 和 `bounded_review.py` 均拒绝以相同工作流 ID 重复提交，也拒绝在已有未完成目录上直接重启。需要先人工确认旧请求已经终结与实际消费量。

## 下一步仍需验证

- 至少 3 份真实源码、多次不同时间窗口的稳定交付测试；条件中不能同时改变模型、thinking 和输出策略后声称单变量因果。
- 生产者/验证器 P6 字节配额的最小修复应先经生产范围回归与部署门禁批准，而非直接在本实验更新中更改。
- 重新完成 B3-R2 的自然缺陷质量评审，评价真正的 SUPPORTED 问题及独立盲评；当质量收益可靠时再考虑内部 Goldfish 路由。
