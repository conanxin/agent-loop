---
title: OpenClaw Command Executor
version: 1.0
author: agent-loop OSS
---

# OpenClaw Command Executor

Hermes-side skill for the **agent-loop** protocol. Handles `BEGIN_HERMES_COMMAND` ingestion, execution, and canonical report generation.

## Role

Hermes receives commands from OpenClaw via the file-based relay, executes them, and writes structured reports back to the filesystem. Telegram is used only for lightweight status notifications (`HERMES_STATUS` + `HERMES_REPORT_PATH`).

## Protocol

### Ingestion

1. Read `BEGIN_HERMES_COMMAND` block from `hermes-commands/<iteration>.md`
2. Validate required fields: `goal_id`, `iteration`, `command_type`, `objective`, `instructions`
3. Parse `stop_conditions` and `validation` rules

### Execution

1. Execute instructions in `working_directory`
2. Record all commands run with exit codes
3. Capture stdout/stderr for validation

### Report Generation

Write canonical report to `hermes-reports/<iteration>.md`:

```
BEGIN_HERMES_REPORT
goal_id: <goal_id>
iteration: <iteration>
status: PASS|PARTIAL|FAIL|BLOCKED
summary: <one-line summary>
changed_files: <list or "none">
commands_run: <list>
validation_result: <structured validation>
commit: <sha or "none">
report_path: <absolute path>
issues: <list or "none">
recommendation: <actionable next step>
END_HERMES_REPORT
```

### Telegram Notification

Return exactly 2 lines:

```
HERMES_STATUS: REPORT_WRITTEN
HERMES_REPORT_PATH: <absolute-path>
```

## Safety Boundaries

- **Never** auto-execute destructive commands
- **Never** modify real project files without explicit approval
- **Never** leak tokens or personal paths in reports
- **Always** verify `git status` is clean after validation tasks
- **Always** use `make validate` (read-only) instead of `make test` or `make build` when checking project health

## Decision Ingestion

When OpenClaw writes a `BEGIN_OPENCLAW_DECISION` file, Hermes can use `agent-loop-relay --decision-path` to update the state machine. This completes the manual-gated loop.

## State Machine

```
INIT → COMMAND_READY → DISPATCHED_TO_HERMES → HERMES_REPORT_WRITTEN → OPENCLAW_JUDGING → DONE
```

Hermes is responsible for the transition: `DISPATCHED_TO_HERMES → HERMES_REPORT_WRITTEN` (via `--report-path`).
