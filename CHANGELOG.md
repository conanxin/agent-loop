# Changelog

## v1.0.0 (2024-06-14)

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
