# EGM B3-R4｜P6 最小候选修复与 M2.7 同输入重复验收

日期：2026-10-27（北京时间）。状态：**CANDIDATE_FIX_VERIFIED_NOT_DEPLOYED**。

本阶段不再增加实验框架：落实 B3-R3 已独立复现的 P6 胶囊长度问题，复用同一个 M2.7 审查程序做两次有上限的重复调用。候选修复位于独立分支 `egm-b3-r4-capsule-limit`；生产工作目录的 `main` 仍为 `1aa219392c0c80b597b328f4b5deb78f9873c8a8`。

## 1. 已实现的最小修复

问题根因：原 `capture()` 只限制原文件 18,000 字节和 650 行，但 `verify()` 另限制序列化后的 JSON 为 40,000 字节。JSON 转义会增大长度；`ensure_ascii=False` 不会取消必须进行的控制字符转义。依据：[Python 官方 JSON 文档](https://docs.python.org/3.13/library/json.html)。

修复只修改 `bridge/evidence.py`：新增共享常量 `MAX_CAPSULE_BYTES = 40000`，在 `capture()` 生成规范 JSON 后检查 UTF-8 字节长度，超限时抛出明确的 `serialized capsule exceeds evidence quota`；`verify()` 引用同一个常量，原拒绝行为不变。

**没有放宽上限，没有改动原文内容、序列化方式、双重 SHA、路径白名单或符号链接规则。** 原先 10,000 个 U+0001 字节可生成 60,194 字节胶囊、随后被验证器拒绝的情况，现在在生成端就被明确拒绝，不会向下游返回一个不兼容的胶囊。

候选代码提交：[bd35e93](https://github.com/conanxin/agent-loop/commit/bd35e932d425b6666723b39edaef430a8c3ca633)。代码 SHA-256：`292710756bd063effac4ccafda2a157d5ca3511e094adafec7699ef796d0eec0`。

## 2. 测试证据：先失败，再修复，再验证

新增 `tests/test_cxpan_p6_capsule_budget.py` 共 8 项真实行为测试。先在原实现运行：3 项失败、5 项通过，三项失败均是“应拒绝超限但没有拒绝”，不是语法错误。实施修复后，新测试与原有 P6 工作流测试合计 **16/16 PASS**。

| 边界或兼容条件 | 验收结果 |
| --- | --- |
| 序列化恰好 40,000 字节 | 正常捕获、验证、双 SHA 通过 |
| 序列化 40,001 字节 | 生成端拒绝；验证器也继续拒绝 |
| 10,000 字节控制符变成 60,194 字节 JSON | 生成端拒绝 |
| Python 字符数 38,393，但 UTF-8 为 40,393 字节 | 按字节正确拒绝 |
| 普通 ASCII、中文、CRLF、引号、反斜杠、空文档 | 规范 JSON 字节及原文保持一致 |
| 原文 18,000 字节、650 行、路径白名单和双 SHA | 原有约束不放宽 |

当前三个真实公开文档逐一比较修改前后输出，**规范 JSON 字节完全一致**：`README.md` 的胶囊 12,755 字节，`docs/SPEC.md` 5,672 字节，`docs/SCHEMAS.md` 5,444 字节。对应摘要保存在 `benchmarks/egm_b3_r4/results_summary.json`。

### 全量回归及一次环境失败

在 linked worktree 直接运行 `make contract-test`，共执行 140 项，其中两项原有 Worker 测试报错：

- `test_claude_error_parses_only_safe_subtype_not_raw_content`
- `test_fixed_repo_validation_uses_allowlisted_unittest_command`

原因已核对：旧 Worker 的仓库识别要求 `.git` 是目录，而 linked worktree 的 `.git` 是文件。这与胶囊代码无关；本阶段没有顺便放宽 Worker 的仓库检查，也没有改掉原测试来制造通过。

将同一个已提交候选放入普通独立 Git 克隆，确认候选代码与测试字节相同后，原五项 Worker 测试通过，再执行完整 `make contract-test`：**140/140 PASS，59.316 秒，exit 0**。保留首次环境失败及第二次完整通过两份回执。

本次通过的是直接运行的全量测试命令，不是生产 `repo.validate.local` 任务的实机验收；其既有 55 秒子进程超时设置没有修改。

## 3. M2.7 重复运行：同输入、同模型、不同会话

复用 B3-R3 原始 `bounded_review.py`（SHA-256 `a067ef862890db79215e6e2356b73564de9697d35da9585a2f928af8b7bc58c2`），在腾讯云串行运行两次，不换提示词、不增加回退调用、不自动重试失败。

| 原文 | B3-R3 首次结构化审查 | 本轮重复审查 | 本轮记录 total tokens |
| --- | ---: | ---: | ---: |
| P6 证据链 | 38.881 秒 | 49.820 秒 | 8,173 |
| P9 受限 MCP | 32.433 秒 | 55.009 秒 | 8,993 |

两次新增调用都为 `COMPLETED`、JSON 可解析，实际模型为 `MiniMax-M2.7`、thinking 为 `medium`，具备 `model.completed`，模型可见工具和工具调用均为 0。与首次运行相比，原文 SHA、完整提示词 SHA 均一致，但会话 ID 不同。

因此在这两份固定片段上，结构化审查累计 **4/4 次完成**（每份两次）。这不是长期 SLA，也不是 EGM 审查质量优于普通审查的证据；本轮耗时比前一次更长，不能把一次成功延伸成性能承诺。

**这些复跑仍针对冻结的旧源码，不是针对候选补丁的模型代码评审。** 候选修复的依据是独立复现和测试，而非模型再次点头。

## 4. 复跑提出新意见，但没有自动成为新缺陷

P6 复跑声称深层目录符号链接未检查。对照完整实现，当前白名单只有 `README.md`、`docs/SPEC.md`、`docs/SCHEMAS.md`，没有未检查的中间目录层级；因此该主张**不适用于现有允许路径**。将来扩展到多层路径时可以重新评估，不能现在当成已存在漏洞。

P9 复跑声称两个客户端可互读安全任务属于越权。对照 `bridge/README.md:282–294` 及 `test_two_clients_submit_bounded_safe_tasks_and_read_same_result`，跨 ChatGPT/Claude 读取同一拥有者的安全任务是明确设计且已有测试的行为；私有历史任务另有拒绝测试。**当前不能据此修改授权逻辑，也不能把它宣传为发现新的越权漏洞。**

这两项由本次助手核对完整源码与现有契约，不是独立人类盲评。它们说明：执行和 JSON 交付可以重复成功，模型的具体缺陷判断仍可能受片段缺失或需求误解影响。

## 5. 交付和不变边界

候选分支只新增最小修复、8 项回归测试、本报告和净化结果摘要。`main`、当前工作目录的 `bridge/evidence.py`、云端 pinned config、现有 Hub/Worker/Gateway 均不因该候选发生变更；没有重启服务或开放公网工具。

验证原件在 `~/.local/state/cx-pan/egm/b3r4-20261027/`。其中普通独立验证克隆包含同一候选提交；日志保存测试失败/成功记录，模型原始回执仅保存在用户本地和腾讯云私有目录。Git 与 Notion 保存结果摘要，不保存敏感配置或完整会话数据库。

**结论：P6 候选补丁已通过全量回归，可进入合并与部署评估；尚未合并或部署。M2.7 + medium 继续作为按需的只读候选配置，不切换生产默认模型。** P9 配额、跨客户端共享和 Worktree 仓库识别均不在本次修复范围内。
