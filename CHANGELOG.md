# Changelog

## Unreleased (2026-10-26)

### P7 restricted MCP gateway and client-scoped credentials
- Added two separately authenticated, stateless MCP Streamable HTTP endpoints (ChatGPT test client and Claude custom connector).
- Added bearer hash comparison, Origin/Host protections, safe capability allowlists, historical task visibility filter, separate daily quotas and Caddy TLS reverse path on the existing web frontend.
- Verified two real public HTTPS client echo roundtrips, whitelisted public source capture and cross-client safe-task result retrieval.
- Explicit compatibility gap: Claude supports fixed header auth; ChatGPT native custom MCP requires OAuth-compatible setup, not yet implemented. Do not claim consumer-chat-UI connection complete.


### P6 allowlisted primary-source evidence and two-model review
- Added exact UTF-8 source capsule with file byte count, line labels and SHA-256, limited to 3 public agent-loop documents; rejects traversal, symlinks, binary data and oversize files.
- Added Hub-verified immutable source parent/result SHA256 for independent local Hermes and cloud OpenClaw evidence-review tasks.
- Added source_review.py operator workflow with deterministic deduplication, source digest verification and explicit path/line citation range check.
- Completed real P6 docs/SPEC.md 5299-byte experiment, independent two-model reviews and SQL evidence provenance checks. No private user file access or remote MCP exposure.


### P5 true three-model chain and private cloud reviewer
- Enabled a real read-only cloud OpenClaw model turn using supported adaptive thinking and pinned deny-all-tools config.
- Added a dedicated Tencent cloud worker that only claims openclaw.model.cloud text-review tasks.
- Added immutable parent task and source SHA-256 validation via an additive task_provenance table, without modifying existing task records.
- Added Claude→Hermes→OpenClaw review_chain.py with persisted receipts, staged stop-on-failure and stable idempotency.
- Verified native OpenClaw session reply, full three-model completed chain, both source hashes and no duplicate model calls.
- Local OpenClaw headless exit-137 remains a separate unverified issue; observed external timeout may explain some previous 137 results.


### P4 real Hermes model and Claude-to-Hermes review
- Found Hermes 0.22.x chat -q session.create regression; confirmed verified -z one-shot model entry works with clarify toolset.
- Added authenticated, strictly text-only Hermes review worker capability and a cross-agent handoff CLI using completed Claude task output.
- Real cloud→local Hermes model task and Claude→Hermes independent review both COMPLETED; stable source ID deduplicates follow-up requests.
- OpenClaw headless agent exec remains blocked with exit 137 and no conclusive local OOM evidence.



### P3 resumable readiness workflow
- Added allowlisted repository validation worker with fixed unit-test command.
- Added operator-run sequential workflow with stable task ids, persisted receipts and optional Claude Code research first.
- Tested real cloud/local 3-stage chain and replay without duplicate execution; model-level Hermes/OpenClaw turns remain blocked.
- Proven 4-stage Claude research + fixed local validation + dual gateway health chain; verified idempotent workflow replay.
- Fixed Claude CLI pilot error_max_budget_usd by making the per-task budget ceiling configurable (default $0.75).

### P2 incremental gateway health and stale-task visibility
- Safe Claude Code failure classification without copying raw unsuccessful model output.
- Added explicit read-only gateway health capabilities for Hermes and OpenClaw;
  no unrestricted agent turns, privileged shell, or configuration changes.
- Added worker heartbeat and execution_health on task read; stale RUNNING
  tasks require review and are never automatically replayed.
- Added isolated negative tests for heartbeat identity and 180s stale detection.
- Preserved the opt-in core/bridge separation and prior task database schema.

### Optional CX-PAN bridge pilot
- Added a loopback-only, bearer-authorized HTTP/SQLite Hub on a separate cloud host.
- Added CLI submit/status/result, outbound WSL2 Worker, and registered echo/Claude Code read-only capabilities.
- Added cloud SSH forward and worker user-service templates; the core manual relay remains independent.
- Passed real cross-host echo, idempotency, read-only Claude Code round-trip and queued-task cloud restart recovery.
- Added four isolated Hub/HTTP regression tests (total 16 core + bridge tests).
- Documented limitations: no MCP/A2A façade yet, no unapproved shell tasks, no retry of interrupted RUNNING tasks.


- Strict canonical field, goal ID, integer iteration, path and decision validation.
- Correct iteration tracking, numeric command sorting, and SHA-256 change detection.
- Isolated positive/negative regression tests and read-only JSON status export.
- Install directly from the checkout without cloning into a nonempty task directory.
- Preserve the manual relay contract; no new network server or auto-execution.


## v1.0.0 (2026-06-14)

### Added
- Initial OSS release
- Manual relay mode with full state machine
- File-based protocol (BEGIN_HERMES_COMMAND, BEGIN_HERMES_REPORT, BEGIN_OPENCLAW_DECISION)
- Telegram transport with 2-line status notifications
- 6 decision types: DONE, NEXT_COMMAND, REPAIR_COMMAND, PARTIAL, BLOCKED, NEEDS_HUMAN_REVIEW
- 11-field canonical report format
- Safety boundaries documentation
- Complete documentation suite (SPEC, STATE_MACHINE, MANUAL_RELAY, SCHEMAS, SAFETY, TROUBLESHOOTING)
- Example goals (minimal-goal, manual-relay-smoke-test)
- Install and smoke-test scripts
- MIT License

### Features
- `agent-loop-init-goal` — Create new goals
- `agent-loop-set-state` — Manual state control
- `agent-loop-show` — Display goal state
- `agent-loop-relay` — State machine relay with multiple modes
  - `--once` — Print command without advancing
  - `--mark-dispatched` — Advance to DISPATCHED_TO_HERMES
  - `--report-path` — Record report and advance to HERMES_REPORT_WRITTEN
  - `--judge-prompt` — Build judge prompt for OpenClaw
  - `--mark-judging` — Advance to OPENCLAW_JUDGING
  - `--decision-path` — Ingest decision and advance to final state

### Safety
- No auto-execution
- No real project modification without approval
- No token or path leakage
- State machine enforcement for decision ingestion
- Git status verification after validation tasks

### Documentation
- README.md with architecture diagram and quick start
- SPEC.md with protocol specification
- STATE_MACHINE.md with complete state diagram
- MANUAL_RELAY_WORKFLOW.md with step-by-step guide
- SCHEMAS.md with formal protocol schemas
- SAFETY_BOUNDARIES.md with red lines
- TROUBLESHOOTING.md with common issues
