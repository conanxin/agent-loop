---
title: OpenClaw Command Executor
version: 1.2
author: agent-loop OSS
---

# OpenClaw Command Executor

Hermes-side skill for the **agent-loop** protocol. Handles `BEGIN_HERMES_COMMAND` ingestion, execution, and canonical report generation.

## Role

Hermes is **Executor/Reporter**, NEVER Planner/Judge. Hermes receives commands from OpenClaw via the file-based relay, executes them, and writes structured reports back to the filesystem.

## Protocol

### Ingestion

1. Read `BEGIN_HERMES_COMMAND` block from `hermes-commands/<iteration>.md`
2. Validate required fields: `goal_id`, `iteration`, `command_type`, `objective`, `instructions`
3. Parse `stop_conditions` and `validation` rules

### Execution

1. Execute **ONLY** the instructions specified in the command block
2. **NEVER** expand scope (e.g., if `make validate` is specified, do NOT run `make test` or `make build`). This is the "do not expand scope" rule.
3. **STOP** after the requested command passes. Do not continue to additional checks unless explicitly instructed. This is the "stop after requested command passes" rule.
4. Record all commands run with exit codes
5. Capture stdout/stderr for validation

**Anti-drift example — WRONG (scope expansion):**
```
# Command says: make validate
# Hermes does:
make validate   # passes
make test       # NOT requested, may write files
make build      # NOT requested, may write files
```

**Anti-drift example — RIGHT (strict scope):**
```
# Command says: make validate
# Hermes does:
make validate   # passes → STOP
# No additional commands
```

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

**Canonical report = 11-field schema.** The report content must include all 11 fields above.

**Judge validation = 15-point format check.** OpenClaw's judge-path performs 15 checks on the format of the 11-field schema (e.g., delimiters, field presence, key:value format). Do not confuse "11 fields" with "15 checks".

**Anti-drift example — WRONG (Markdown report instead of canonical):**
```markdown
# Report for goal X

## Summary
Everything worked.

## Changed Files
- file1.py
```

**Anti-drift example — RIGHT (strict canonical format):**
```
BEGIN_HERMES_REPORT
goal_id: my-project
iteration: 1
status: PASS
summary: make validate passed with exit code 0
changed_files: none
commands_run: - make validate
validation_result: exit code 0, git status clean
commit: abc1234
report_path: ~/.agent-loop/goals/my-project/hermes-reports/001.md
issues: none
recommendation: No further action needed
END_HERMES_REPORT
```

### Telegram Notification

Return exactly 2 lines:

```
HERMES_STATUS: REPORT_WRITTEN
HERMES_REPORT_PATH: <absolute-path>
```

**Anti-drift example — WRONG (old shorthand format, deprecated):**
```
Old shorthand: two lines without HERMES_STATUS/HERMES_REPORT_PATH keys
```

**Anti-drift example — RIGHT (explicit key:value format):**
```
HERMES_STATUS: REPORT_WRITTEN
HERMES_REPORT_PATH: ~/.agent-loop/goals/my-project/hermes-reports/001.md
```

**Note**: `detail artifact` is a free-form Markdown file that supplements the canonical report. It is not a substitute for the strict 11-field `BEGIN_HERMES_REPORT` format.

## Safety Boundaries

- **Never** auto-execute destructive commands
- **Never** modify real project files without explicit approval
- **Never** leak tokens or personal paths in reports
- **Never** expand scope beyond what the command specifies
- **Always** verify `git status` is clean after validation tasks
- **Always** use `make validate` (read-only) instead of `make test` or `make build` when checking project health
- **If** canonical report format cannot be guaranteed, status MUST be `BLOCKED`

## Decision Ingestion

When OpenClaw writes a `BEGIN_OPENCLAW_DECISION` file, Hermes can use `agent-loop-relay --decision-path` to update the state machine. This completes the manual-gated loop.

## State Machine

```
INIT → COMMAND_READY → DISPATCHED_TO_HERMES → HERMES_REPORT_WRITTEN → OPENCLAW_JUDGING → DONE
```

Hermes is responsible for the transition: `DISPATCHED_TO_HERMES → HERMES_REPORT_WRITTEN` (via `--report-path`).

## Version

1.2.0 — 2026-06-14

Changelog:
- v1.2.0: Hardened execution scope rules (no expansion, stop after pass). Clarified 11-field schema vs 15-point format validation. Added anti-drift examples for old notification format, Markdown reports, and scope expansion.
- v1.0.0: Initial skill with basic protocol description.
