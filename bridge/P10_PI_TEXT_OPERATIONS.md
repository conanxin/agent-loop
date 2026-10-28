# CX-PAN P10-H / P10-I — xinhailin Pi text-only cloud task path

## Scope and actual status (2026-10-28)

- **Internal cloud task:** `pi.text.cloud` / `pi.text`, integrated with the existing CX-PAN loopback Hub, Task Ledger and a dedicated worker.
- **Worker:** `cx-pan-pi-text-worker.service` as ubuntu systemd user service. A single worker processes Pi tasks serially via `/home/ubuntu/cxpan-xinhailin/dispatcher.py` and Tailscale SSH to the Windows `xinhailin` Pi 1.4.0.
- **Real model test:** Task `7b9c80a9-1508-482b-bd63-8378951a479e` completed with MiniMax-M2.7 response `PI_HUB_WORKER_OK`; duplicate submission returned the same task.
- **Public OAuth MCP endpoint:** `https://www.conanxin.com/cxpan/chatgpt-pi/mcp`; requires *only* `tasks:pi_text` for access. This endpoint exists but the user has not completed real ChatGPT OAuth authorization for Pi yet.
- **Legacy safe OAuth MCP endpoint:** `https://www.conanxin.com/cxpan/chatgpt/mcp`, unchanged `tasks:safe`, cannot invoke the Pi tools. The independent CX-PAN MCP Test connection still passed `agents_list` after deployment.

## Limits and scope separation

- Pi task input: 4–1200 Unicode characters (UTF-8 transport).
- Model: fixed `minimax-cn/MiniMax-M2.7`.
- Daily worker cap: **6 new Pi tasks/day (UTC)**, persisted in `~/.local/share/cx-pan/pi_text_daily.sqlite3`.
- Pi mode: `--no-tools --no-mcp --no-extensions --no-skills --no-session --print`; no general remote shell tool offered to the ChatGPT client.
- Hub requesters: `cxpan.internal.pi` for internal trusted testing and `mcp.chatgpt.pi` for separately authorized public MCP. Task IDs, runs, receipts and duplicate prevention stored in the existing Hub.
- OAuth scopes and audience are disjoint: `tasks:safe` belongs to the original MCP resource, `tasks:pi_text` belongs to the new MCP resource. The protected gateway validates resource+scope on every request. Both endpoints require authentication, no anonymous Pi tool.

## Real user connection (not yet done)

In ChatGPT Plugins choose **Add custom MCP server** and enter:

- Name: `CX-PAN Pi Text`
- Server URL: `https://www.conanxin.com/cxpan/chatgpt-pi/mcp`
- Authentication: OAuth
- Registration: Dynamic Client Registration (DCR), not CIMD
- Scope: **`tasks:pi_text` only**; do not keep `tasks:safe` checked for this Pi connection.
- OIDC: disabled (not advertised).

Only after the user is ready to create this connection, from their own authenticated Tencent OrcaTerm terminal:

```bash
sudo -n -u ubuntu python3 /home/ubuntu/cxpan-owner/connect_chatgpt_pi.py
```

The user enters START, launches the ChatGPT connection while DCR is open, copies the one-time Request ID into the terminal's hidden prompt, checks the **pi_text scope/resource and model cost notice**, and explicitly types APPROVE. Never paste Request IDs or OAuth tokens into ChatGPT. This dedicated approval helper does not authorize the existing safe plugin to invoke paid models.

After connecting, ChatGPT should use `pi_capabilities`, then `pi_text_submit`, `pi_text_get`, `pi_text_result` and verify one real Pi answer. Only then can we validate calling these tools **with the main WSL computer offline**.

## Important remaining hardening

The cloud SSH transport currently authenticates as the Windows administrator-group account `haili`; the Pi CLI disables its tools, and the cloud MCP does not expose arbitrary SSH, but that is **not an OS-level sandbox**. For any future file/command tasks, use a non-administrator Windows account or a purpose-built restricted broker before expanding scopes. No private files/NAS operations are permitted by this text-only interface.

## References

- [OpenAI Plugins authentication](https://developers.openai.com/plugins/build/auth)
- [OpenAI Plugins connect and test](https://developers.openai.com/plugins/deploy/connect-chatgpt)
- [P10 Notion ledger](https://app.notion.com/p/40734a28189a812d8f7ee3044d62b2a3)
