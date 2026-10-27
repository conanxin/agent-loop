# CX-PAN P8｜OAuth 2.1 运维与客户端接入（2026-10-27）

> **P9 增量（2026-10-27）**：正式创建个人私有 CX-PAN 插件，补充一条可信交互式终端连接脚本及 OAuth Client 审计/撤销。P8 的合成测试与下文状态为历史阶段；[P9 最终使用手册](P9_CONNECTOR_OPERATIONS.md) 为最新说明。

## 当前状态

P8 已上线基于官方 Python MCP SDK 的 OAuth 授权服务器：授权码、PKCE S256、动态客户端注册（DCR）、短期访问令牌、刷新轮换和吊销。真实公网 HTTPS 合成测试完成了注册 → 所有者批准 → token 交换 → MCP 初始化和 Echo 任务 → 刷新 → 撤销。合成测试后，云端没有活动的测试 OAuth 令牌。

**与消费版聊天 UI 的区别：** 这些验收不等于 ChatGPT Plugins 或 Claude Chat 已经安装。ChatGPT 首次连接需要你在 ChatGPT 自己的插件界面安装，并通过可信 SSH 终端亲自批准其 OAuth 请求；Claude Chat 仍需你在客户端设置里添加 P7 自定义连接器。

## OAuth 架构与接口

- ChatGPT MCP：`https://www.conanxin.com/cxpan/chatgpt/mcp`，Caddy 443 → 仅回环 `127.0.0.1:18488` 的 `cx-pan-mcp.service`。
- OAuth issuer：`https://www.conanxin.com/`，标准授权端点 `/authorize`、`/register`、`/token`、`/revoke`，受信任 owner approval 页面 `/owner-approve`。
- SDK 授权服务器：`cx-pan-oauth.service`，仅回环 `127.0.0.1:18489`。
- OAuth AS 元数据：`https://www.conanxin.com/.well-known/oauth-authorization-server`。
- MCP 受保护资源元数据：`https://www.conanxin.com/.well-known/oauth-protected-resource/cxpan/chatgpt/mcp`。
- 令牌固定绑定 `resource=https://www.conanxin.com/cxpan/chatgpt/mcp` 和唯一 `tasks:safe` scope；无通用 shell、删除、私人 NAS 文件、付费模型权限。
- OAuth Client DCR 只允许 ChatGPT 官方域名的正式 callback-ID-specific / 稳定 redirect 地址，其他任意域名均拒绝。PKCE 只支持 S256。
- OAuth token 是 256-bit+ 随机不透明字符串，服务器 SQLite `oauth.sqlite3` 只储存 SHA-256 摘要，不储存 access/refresh 原文。Access 15 分钟有效，Refresh 30 天有效、每次旋转；吊销 Token Family 后访问令牌与刷新令牌均失效。
- Caddy 改动前备份于 `/etc/caddy/Caddyfile.cxpan-pre-p8-20261027`，未改动原网站主页、现有 Agent Gateway / Worker。

## 高安全默认：客户端注册窗口关闭

为防止陌生人耗尽动态客户端注册名额，公网 DCR **默认关闭**。只有持有可信腾讯云 SSH 权限的所有者能临时打开最长 30 分钟的注册窗口，窗口到期自动关闭。

### ChatGPT 插件首次连接：需要用户明确操作

1. 从用户本地 WSL2 可信终端短时开启 OAuth 客户端注册：

~~~bash
ssh tencent 'python3 ~/cx-pan-hub/oauth_server.py owner registration-open --minutes 10'
~~~

2. 在 ChatGPT Plugins 点击 `+` → `Add custom MCP server`，输入 `https://www.conanxin.com/cxpan/chatgpt/mcp`，选择标准 OAuth。如页面提供注册选项，可选 DCR；如果必须用 CIMD，则本版尚未实现，不能假称已兼容。
3. 浏览器授权页面跳到 `https://www.conanxin.com/owner-approve?request=...`。页面仅展示一个高熵 Request ID、请求的客户端回调和 `tasks:safe` 权限，**不会自动批准**。不要把 Request ID 复制进聊天或 GitHub。
4. 仔细核实请求确实来自你刚开始的连接，再在受信任 WSL2 终端输入：

~~~bash
ssh tencent 'python3 ~/cx-pan-hub/oauth_server.py owner list'
ssh tencent 'python3 ~/cx-pan-hub/oauth_server.py owner approve <Request-ID-from-the-browser>'
~~~

若不是你发起的请求，改用 `owner deny <Request-ID>`。Request ID 由网页本人读取，真实用户审批永远需要自己的明确操作。
5. 授权网页自动刷新完成 OAuth 回调后，从 ChatGPT Plugins 里试用 `agents_list`，然后试用安全 Echo 任务。只有 ChatGPT UI 真正显示工具并返回任务完成结果，才能把 `CHATGPT_NATIVE_OAUTH_CONNECTED` 标为 PASS。
6. 不论结果怎样，关闭客户端注册窗口：

~~~bash
ssh tencent 'python3 ~/cx-pan-hub/oauth_server.py owner registration-close'
~~~

**注意：** 当前 ChatGPT 原生客户端安装/登录尚未实测，以上是下一次需要用户在自己 UI 中完成的步骤。不要用 No Authentication 绕过已有 OAuth，也不要通过聊天发送 OAuth Token 或管理员请求。

## Claude Chat 独立连接

Claude P7 MCP URL 继续使用 `https://www.conanxin.com/cxpan/claude/mcp`，配备另一枚独立 Bearer 凭据，保存在用户 WSL2 `~/.config/cx-pan/connectors/claude.bearer`（0600）。在 Claude `Customize → Connectors → Add → Custom → Web` 中输入 URL 并配置对应认证。未完成真正 Claude Chat UI 的安装，不宣称已连接。

## P8 验收证据与边界

- 生产合成 OAuth DCR 客户端在公网 HTTPS 上完成：标准 discovery、临时注册、由可信服务器 CLI 批准一个测试专用授权、S256 换令牌、标准 MCP initialize 和 safe Echo 任务返回 COMPLETED、刷新轮换、吊销 token family；最终数据库 active access / refresh 数均为 0。
- DCR 注册窗口随后升级为**默认关闭 + 所有者短时开启**，已单独通过隔离测试并上线；不会自动批准真实 ChatGPT 客户端。
- 真实用户聊天 UI 尚未参加上述合成测试；OpenAI OAuth SDK DCR 现能工作，但 CIMD（OpenAI 当前首选）的兼容与真实插件 UI 连接仍需单独验收。
- 本阶段未授权任何新的模型付费调用、终端执行、私人资料/NAS/硬盘访问。现有 P7 Claude Chat 使用的独立 Token 继续可正常查询安全任务。
- 这是个人研究服务中的 SDK-backed 自建授权服务器，尚未完成第三方独立渗透测试；在升级到私人数据/高权限 Agent 前，建议再评估既有成熟 IdP 与独立安全审计。

## 回滚与排障

- 查看云端状态：`ssh tencent 'systemctl --user is-active cx-pan-oauth cx-pan-mcp; python3 ~/cx-pan-hub/oauth_server.py owner list'`。
- 如有可疑注册请求，保持 `registration-close` 并使用 `owner deny`，不批准未知回调。
- 需要 P8 HTTPS OAuth 路由下线：先关闭 DCR，停止 `cx-pan-oauth.service`，使用备份 `/etc/caddy/Caddyfile.cxpan-pre-p8-20261027` 恢复 Caddy 配置并运行 `caddy validate` / `systemctl reload caddy`，原有 `/cxpan/*` P7 路由、官网与 Hub 不应受影响。
- 不通过直接删除 `oauth.sqlite3` 来撤销现有用户授权；应使用 `/revoke` 及客户端断开连接流程。

来源：
- [OpenAI 插件 OAuth 授权规范](https://developers.openai.com/plugins/build/auth)
- [OpenAI MCP 接入](https://developers.openai.com/api/docs/mcp)
- [MCP 授权协议](https://modelcontextprotocol.io/specification/2025-11-25/basic/authorization)
- [Claude 连接器说明](https://support.claude.com/en/articles/11176164-use-connectors-to-extend-claude-s-capabilities)
