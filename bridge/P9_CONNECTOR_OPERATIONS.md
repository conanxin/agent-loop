# CX-PAN P9｜私有 ChatGPT 插件、OAuth 客户端生命周期与本人授权接入

阶段日期：2026-10-27。P8 官方 MCP SDK OAuth 已在腾讯云运行，本阶段强化客户端管理并创建个人私有插件。

## 1. 私有 ChatGPT 插件（已创建，未安装/授权）

- 插件 ID：`plugins_6ae016c0348881918f74bd2c023ab5fe`。
- 版本 `0.1.0`，可见性 `PRIVATE`、scope `USER`。
- **个人插件链接：** https://chatgpt.com/plugins/plugins_6ae016c0348881918f74bd2c023ab5fe
- OAuth 类型：`client.mode=dcr`，资源 `https://www.conanxin.com/cxpan/chatgpt/mcp`，`baseScopes=["tasks:safe"]`。
- 插件包不含访问令牌、客户端密钥、OAuth Request ID 或本地账户凭据。
- 模型/Agent 付费调用、任意终端、NAS 和私人资料均不开放到此插件；其四项安全工具仍是 agents_list、task_get、task_result、task_submit_safe。
- 创建插件与真正从 ChatGPT 账户安装/连接是不同状态。**只有用户本人在 ChatGPT Web 完成安装和 OAuth，且实际调用工具获得回执，才可标记 CLIENT_UI_CONNECTED。**

## 2. 最简本人连接流程（仅可信 WSL2 交互式终端）

打开 ChatGPT **网页端**，准备访问上面的私有插件链接。在你自己控制的 WSL2 终端运行：

`python3 ~/workspace/projects/agent-loop/bridge/connect_chatgpt.py`

该向导依次：
1. 要求在真实终端输入 `START` 才暂时开放 OAuth DCR，最多 10 分钟；
2. 请用户在 ChatGPT Web 的私有插件页面操作 Connect/OAuth；
3. 用户在浏览器看到 `www.conanxin.com/owner-approve` 页面和一次性 Request ID 后，在**自己的终端隐藏输入**该 ID，绝不通过 ChatGPT 对话粘贴；
4. 服务器查询该请求的 Client、Callback、Scope、资源、到期时间，只有全部为允许的 ChatGPT 回调、`tasks:safe`、正式 MCP URL 才允许继续；
5. 向导要求用户输入精确的 `APPROVE`，否则不批准；自动关闭注册窗口（无论成功、用户取消还是异常）。
6. 安装完成后才在 ChatGPT 里查看 `agents_list`、提交安全 Echo、查询 COMPLETED；此验收需要真正的 ChatGPT UI 回执。

**重要：** ChatGPT 账户／工作区权限可能不允许直接安装自定义 MCP 连接，尤其写操作的支持随方案不同。如果插件界面不可安装或不显示 OAuth，当前服务端测试通过也不等于账户可使用。不要绕过 OAuth 改成匿名，原 CXRE Personal 已可继续为 ChatGPT 操作本地/云端任务。

## 3. P9 生产安全增强

- OAuth 动态注册仍保持默认关闭、所有者按需短时开放。新加入 **5 个客户端／30 分钟** 的额外注册数量限制，且每个客户端最多 **8 个未处理的授权请求**、系统全局最多 30 个未处理授权请求，降低刷接口和资源占用风险。
- 标准 OAuth discovery 的 `token_endpoint_auth_methods_supported` 已准确声明 `none`（DCR 公共客户端 PKCE 已实测可用）、`client_secret_post`、`client_secret_basic`，避免客户端只看到不完整的服务端能力。
- P9 增加受信任终端的 OAuth `owner clients`（不输出 client_secret）、`owner request-info <Request-ID>`（核对请求权限、callback、有效期）、`owner audit`（有限事件日志）、`owner revoke-client <client_id>`（一次性撤销该 Client 的所有 access/refresh tokens、未兑换授权码和待审批请求，并删除 Client 注册）。
- 审计事件只储存发生时间、事件名称和 client_id，不储存原始令牌、授权码或请求 ID。OAuth Token 数据库继续为 0600，且本次部署前通过 SQLite online backup 创建了独立备份。
- MCP SDK 工具列表增加 `readOnlyHint`／`destructiveHint` 注释：查询三个工具声明为 read-only，`task_submit_safe` 声明为受限、非破坏性、幂等的**写入队列操作**，不把创建任务假装为只读。
- 生产合成 HTTPS DCR / PKCE / 安全 Echo / Refresh / Revocation 流程再次通过，**合成客户端已清除**、Active Access=0、Active Refresh=0、注册 CLOSED、未决授权=0。
- 所有现有 Hermes/OpenClaw Gateway、CX-PAN Worker、云端 Hub、P7 Claude Bearer 入口和静态网站原路由均继续运行。

### 可用的只读管理命令（不会显示密钥）

```bash
ssh tencent 'python3 ~/cx-pan-hub/oauth_server.py owner list'
ssh tencent 'python3 ~/cx-pan-hub/oauth_server.py owner clients'
ssh tencent 'python3 ~/cx-pan-hub/oauth_server.py owner audit'
```

**撤销真实 OAuth 客户端会使其永久断开连接，需要重新注册并重新本人授权。** 本阶段未撤销任何真实用户的客户端，只清理了自己创建的合成安全测试 Client。未来若要执行 `revoke-client`，必须由用户确认准确 Client ID 和目的后再在可信终端操作。

## 4. 本阶段真实测试与证据

- OAuth 客户端生命周期、注册配额、待审配额、Owner 逐请求元数据、整套 Token/Codes 撤销：新增 5 项回归测试 PASS。
- 单命令交互安全：必须有 TTY、不能默许审批、必须输入 `START` 与 `APPROVE`、Request ID 字符白名单、错误 Scope / Audience / Redirect / 过期拒绝、异常最终关闭注册：新增 7 项测试 PASS。
- 既有 P8 OAuth + 资源服务 8 项安全测试也继续通过；全套总回归 `81` 项（最终发布验收以实际测试日志为准）。
- 腾讯云 OAuth 数据库部署前有私有 SQLite 备份 `oauth-pre-p9-20261027.sqlite3`；服务继续只监听回环，Caddy 443 作为唯一公网 HTTPS 入口。
- 线上重新获取元数据返回正确 token endpoint Auth Methods；合成客户端经公网安全 Echo 往返通过，刷新/撤销成功，数据库最后 0 个有效测试令牌、0 个登记 Client。

## 5. Claude Chat 真实连接的边界

Claude 端仍为 `https://www.conanxin.com/cxpan/claude/mcp`，独立 Bearer 凭据仅在用户 WSL2 权限 0600 文件 `~/.config/cx-pan/connectors/claude.bearer` 中。Claude Chat 网页真实安装需要用户操作自己的 Connectors 页面。本阶段没有替用户在浏览器点击连接，也没有证据证明真正的 Claude 网页聊天端已调用此 MCP。

## 6. 下一步 P10：真正双客户端安装验收

- 用户用私有插件入口在真实 ChatGPT Web 安装、本人 OAuth 授权并调用安全工具。若插件权限不足，先确认账户／工作区支持范围；不要假装已安装。
- 用户在 Claude Chat Web 创建自定义 Connector，经其官方支持的请求头／OAuth 完成本人授权与一次 Echo 任务，记录真实 UI 调用来源。
- 进一步扩展 P10：OAuth 客户端访问日志审计、必要时采用现成 IdP 与 CIMD（目前使用 DCR）；完成第三方安全评估前不增加私人档案、NAS 和付费执行能力。
- 本研究的下一阶段应继续增量写入 Notion；Task Ledger 仍在 SQLite，不要把 Notion 当成排队服务。

[OpenAI 官方自定义 MCP 连接要求](https://help.openai.com/en/articles/12584461-connecting-custom-mcp-servers-in-chatgpt)｜[官方 OAuth 文档](https://developers.openai.com/plugins/build/auth)｜[插件打包与 DCR](https://developers.openai.com/plugins/build/plugins)。
