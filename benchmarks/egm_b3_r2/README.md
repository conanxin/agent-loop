# EGM Gate B3-R2｜无植入错误的真实源码冷读对照

本阶段使用来自 `conanxin/agent-loop` Git 提交 `231290845a4117ba7e05ac5226b802b4faf11045` 的真实、未修改源码及规范文档，冻结三个问题域：状态转移与 CLI 实现、P6 证据完整性、P9 公网受限 MCP/OAuth 边界。

## 与 B3 第一轮有什么区别？

- B3 第一轮用了“真实文档 + 人为种入六处明显矛盾”的测试副本；结果是普通审查和 Goldfish 各 6/6，未见增量收益。
- 本轮 **没有注入任何错误**。因此没有预知的六条正确答案；模型提出的缺陷**必须由第二个审查流程按照真实源码证据核验**，不能靠生成数量作比较。
- 所有模型看到相同的、带原始路径与原始行号的来源材料，保留来源文件的 SHA-256。没有传入先前评论、Goldfish 标签对应的另一组输出、用户私人记忆或未授权文件。

## 三种输入/运行条件，不能混算

1. `manifest.json`、`packets/`、`run_cloud.py`：完整的定向源码摘录，单次 MiniMax M3.1 Flash `adaptive` 审查。其大上下文要求可能影响执行稳定性。
2. `manifest_compact.json`、`compact_packets/`、`run_compact.py`：更短摘录，但首批指定了该模型不支持的 `--thinking low`；这属于**模型配置验证失败**，不能当作审查质量失败。
3. `manifest_compact.json`、`compact_packets/`、`run_compact_adaptive.py`：紧凑摘录、受支持的 `adaptive`，作为后续主要评价条件。它与 1 的上下文范围不同，也不能直接作同一种审查条件下的质量比较。

全部运行均使用原有只读运行入口创建的私有临时配置，关闭 `contextInjection` 和 `toolSearch`，不授予外部工具使用权限。对应执行 SHA、原始输出、SQLite、Token 统计只保存在本地/腾讯云受限状态目录。

## 真实问题怎样评价？

预定方案写在 `PROTOCOL.md`。所有模型 findings 的严格 JSON 进入 `prepare_blind.py`，统一匿名化并打散，独立审查者不应知道它们来自普通审查还是 Goldfish。自动程序只校验原路径、行号是否属于冻结片段；不能证明语义。第二审查者把问题判为 SUPPORTED / PARTIAL / UNSUPPORTED / UNCERTAIN，并把重复问题归为同一可执行修复簇。

只有能由源文件证明确有影响、又不与同组普通审查重复的 Goldfish finding，才可称为其增量发现。对此还必须明确“独立模型核查”不是独立**人类**盲评。

## 运行、成本与可靠性

`run_cloud.py` 和 `run_compact_adaptive.py` 设计上各有 3 案例 × 2 策略 × 2 重复 = 12 个计划位置，但**计划次数不等于实际完成次数**。任何超时、空输出、配置失败都保留并禁止用相同工作流 ID 盲目再次计费。少于完整配对则报告部分完成，不能计算跨全三案例的质量差距。

`score_delivery.py` 负责将交付成功率、引用范围、Token、耗时与缺失结果区分开，`prepare_blind.py` 提供独立复核输入。所有以模型生成的“零问题”也必须是合法、成功交付的结果，不能由运行失败倒推。

## 应用决策

在未经复核的安全候选问题不能证明为真正的程序缺陷、模型执行又不稳定时，不应注册常驻的 EGM Router，不应改动用户已有 CX-PAN P9 OAuth/MCP、Hub、Gateway、NAS 或 Telegram 服务。简单任务继续单 Agent 优先；高风险设计用人工明确触发的独立 Goldfish，待新的真实项目与跨模型复核证明其成本价值。
