# EGM-R2 Gate B2｜历史会话、系统提示词与工具策略真实审计

研究日期：2026-10-27（北京时间）。结论：B2 在测试过的范围内通过；不能宣称所有来源零泄漏；B3 质量 Benchmark 未执行。原有 CX-PAN 与 P9 公网 MCP 均未扩权。

## 一、目标、证据与基线

Gate B1 只验证合成项目规则文件的注入隔离。本轮补充三个层次：历史会话（显式恢复和全新会话对照）、保存的模型消息和编译提示词、OpenClaw 实际工具事件。测试词是无敏感意义的随机英文单词组合。原值、原始模型结果和 SQLite 只存所属主机私人目录 ~/.local/state/cx-pan/egm/；Git 与 Notion 只存工作流 ID、SHA 摘要、统计与裁定。

## 二、Hermes：真正的历史恢复与新会话对照

WSL2 机器 DESKTOP-3A8N7VN；Hermes v0.22.5；工作流 egm-b2-hermes-history-20261027；全部通过 chat -Q --ignore-rules --source tool -t clarify。只有恢复组传入 --resume 指定的 session ID。

| 阶段 | 模型耗时 | 是否读取先前随机词 | 本轮来源词 |
| --- | ---: | --- | --- |
| 新建 seed | 22.569 秒 | 将测试词写入该会话 | 不适用 |
| 明确恢复 resume | 36.498 秒 | 是 | 是 |
| 全新 fresh、无 --resume | 13.567 秒 | 否 | 是 |

seed 和 resume：local-5393a8ecc0b1f091a5c2ad52b1b069d10f4f5d83b7a2bc40d725fc91a0dd1365。
fresh：local-2769ff7c8bff06ac27e56a03a609b78d8ca03ecd53aefc05b8e1cb80dbc3fa6c。

SQLite ~/.hermes/state.db 定向只读核验：恢复过的原会话有 4 条消息，新会话只有 2 条。旧词出现在原会话的第一条 user 消息及恢复后的 assistant 消息中；新会话的 user、assistant 消息均无旧词。两组 tool_call_count 均为 0，source=tool，parent_session_id 均为空。数据库中的 system_prompt 字段为 NULL，不能由此推断实际编译提示词不存在。

本轮主推理 usage：seed+resume 共 2 次模型 API 调用，记录 input 6011 / output 30 tokens；fresh 一次，input 4607 / output 19 tokens。标题生成另有记录。费用字段为 unknown；estimated_cost_usd=0 不能解释为真正零成本。

Hermes 源码还确认了：旧的 -z 单轮路径并未显式传入 skip_context_files/skip_memory，而 chat --ignore-rules 由 cli_agent_setup_mixin.py 传入这两个限制。因此 Goldfish 应使用后者，且不得传入 --resume。

裁定：PASS_CONTROLLED_HISTORY，仅限实际测试的会话隔离。

## 三、腾讯云 OpenClaw：全新 headless 会话

VM-0-4-ubuntu；OpenClaw 2026.10.3，工作流 egm-b2-cloud-history-20261027。

| 阶段 | Session ID | 耗时 | 结果 |
| --- | --- | ---: | --- |
| seed | 26386dd5-db49-4f17-b921-379f0dbb47fd | 21.903 秒 | 写入合成历史词 |
| fresh | cc2a5d04-d19d-461a-874b-64638a478f81 | 19.899 秒 | 没有返回旧词，返回合法来源词 |

状态均为 COMPLETED，裁定 SUPPORTING_FRESH_RUN_ONLY：这里没有类似 Hermes 的显式 --resume 正向对照，因此证据等级较弱。

安装版 dist/agent-exec-Dc4FDCkU.mjs 的实码核查：每次 agent exec 创建新的 randomUUID；未指定 --state-dir 时创建临时状态目录；使用 oneShotCliRun；正常运行完成后删除临时状态。说明这条 headless 路径设计上就是独立、一次性运行，不等同于长期 Gateway 会话。

## 四、SQLite 工具追踪：发现并验证一项真实策略例外

本次添加保留型 --state-dir 追踪工具：使用完全独立的合成工作目录，在 agent exec 完成后只读检查 openclaw-agent.sqlite 的 transcript_events、trajectory_runtime_events、message_tool_run_outcomes 和本实验状态库的 audit_events。JSON envelope 缺少 toolSummary 时，不得自动判断 0 调用。

### A：普通文本调用

工作流 egm-b2-cloud-trace-20261027，20.842 秒，session bdbc8e38-7277-4c27-b483-fbdacb441c9b，COMPLETED。
会话轨迹 6 个 transcript 事件，包括一条 user、一条 assistant 文本；7 个 trajectory 事件，包括 context.compiled、prompt.submitted 和 model.completed。工具 call/result、toolMetas 与工具执行结果都为 0。

但是编译后的模型工具定义包含 tool_call、tool_describe、tool_search，session.started.toolCount=3。即使旧配置写着 tools.deny=["*"]，依然存在可见的工具发现控制接口。单次没有使用，不代表完全无法使用。

### B：工具发现接口挑战

工作流 egm-b2-toolchallenge-20261027，29.894 秒，session 398071d1-3243-4ae3-bfac-7d723c59a188，COMPLETED。
给模型的唯一附加请求是尝试查询一个合成、并不存在的工具名称。真实轨迹存在 1 次 tool.call 与 1 次成功的 tool.result，工具名 tool_search，结果为空列表。JSON envelope 的调用计数也为 1。

这证实旧 pinned 配置未阻止该内置工具发现接口的实际执行；但没有证明 Shell、文件操作或外部网络工具可执行。不可把“元工具搜索成功”夸大成敏感执行权限被突破。

官方资料：[OpenClaw Tool Search](https://docs.openclaw.ai/tools/tool-search) 和 [OpenClaw Tool Policy](https://docs.openclaw.ai/gateway/config-tools/tool-policy)。最新文档部分调度名称为 dispatch_action，本机版本的控制接口仍名 tool_call，实施时需以已安装版本为准。

### C：临时关闭 Tool Search

仅在独立测试配置中额外设置 tools.toolSearch=false，保留原 tools.deny=["*"] 与 contextInjection=never，未改旧的 pinned 生产配置。

工作流 egm-b2-notoolsearch-20261027，23.391 秒，session 0de1d510-2ce9-4ebf-b699-2a9dba0f31ec，COMPLETED。
即使模型被要求尝试 tool_search，实际编译的工具 schema 为空、session.started.toolCount=0、工具调用与结果事件均为 0。

**建议：未来的 EGM 专用云端配置必须同时设置工具拒绝策略、toolSearch=false、contextInjection=never。** 不要只继承旧 P5 审查 Worker 的 deny=["*"] 然后声称无任何工具。

## 五、实际编译的 system prompt 正反对照

工作流 egm-b2-compiledprompt-20261027，同一合成工作目录、相同用户提问，分别设置 contextInjection=always 和 never。两侧都在临时配置中额外禁用 Tool Search，保留独立状态数据库。

| 检查 | 允许注入 control | Goldfish never |
| --- | --- | --- |
| 模型编译 systemPrompt 含仅存在于项目规则中的随机词 | 是 | 否 |
| 模型实际回答含该环境词 | 是 | 否 |
| 模型回答可见本轮合法来源词 | 是 | 是 |
| context.compiled 中 prior messages 数量 | 0 | 0 |
| 实际工具调用事件 | 0 | 0 |
| 耗时 | 19.683 秒 | 19.757 秒 |

控制会话：6eecd36b-1bf9-49c3-b617-314e624608f0。Goldfish 会话：9c069eed-78a4-4222-a226-ef5fb1ec74de。

原始脚本最初裁定 INCONCLUSIVE_OR_FAIL，原因是 SQLite 中保存的 prompt.submitted 用户来源词被替换为 SOURCE_WORD=[redacted]，不是原值。保存原始回执后，用真正的 systemPrompt 标记差异、模型来源词回显、新 session ID、prior messages=0 和 tool events=0 不收费重新核查，另外生成 receipt-reassessment.json，裁定 PASS_COMPILED_PROMPT_AB。原始不利裁定仍留存，并非直接改写成成功。

## 六、实施状态与后续问题

| Gate | 当前裁定 |
| --- | --- |
| B1 项目规则注入对照 | PASS |
| B2 Hermes 历史恢复与新会话 | PASS（测试范围内） |
| B2 Cloud 新 headless 会话 | SUPPORTING_PASS |
| B2 Cloud systemPrompt 正反对照 | PASS（测试范围内） |
| B2 Cloud 旧 Tool Search 策略 | 确认例外：成功 1 次内置 tool_search |
| B2 Cloud 临时禁用 Tool Search | PASS：0 model-visible tools、0 实际 tool events |
| B2 所有外部记忆、Provider 侧隐含上下文 | 尚未穷尽 |
| B3 多规格设计审查质量、误报、时间、费用对照 | 尚未开展 |

目前只有受控实验，没有部署谷歌 EGM 官方插件，没有为内部 Hub 注册新 Goldfish targets，没有修改 P9 公网 MCP/OAuth 或现有 Gateway/Telegram。当前可给出 **B2_SCOPED_PASS**，不能给出全环境、全提供方的 COMPLETE_ZERO_LEAKAGE 证明。

下一阶段应制定独立 EGM 专用云端配置，再进行 B3 普通审查与 Goldfish 的同规格盲评；至少三份设计规格，人工核定真问题与误报，记录真实可取得的调用量和用时。只有证明价值才加入 CX-PAN 内部 Router。

## 七、代码、回执和来源

工程代码：bridge/egm_history_ab.py；bridge/egm_cloud_trace_probe.py；bridge/egm_cloud_trace_inspect.py；bridge/egm_cloud_prompt_ab.py。离线测试：tests/test_egm_gate_b2.py；tests/test_egm_trace_inspect.py；tests/test_egm_compiled_prompt.py。

Hermes 私有回执：~/.local/state/cx-pan/egm/egm-b2-hermes-history-20261027/receipt.json。云端私有回执与 SQLite：~/.local/state/cx-pan/egm/egm-b2-cloud-history-20261027、egm-b2-cloud-trace-20261027、egm-b2-toolchallenge-20261027、egm-b2-notoolsearch-20261027、egm-b2-compiledprompt-20261027。

原始随机词、完整模型提示词与 SQLite 原始记录不写入 Notion 或公开 GitHub。后续研究继续写入既有 EGM Notion 主档：https://app.notion.com/p/40634a28189a81a4a14dc301f54e4af9 。
