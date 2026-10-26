# Changelog

## Unreleased (2026-10-26)

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
