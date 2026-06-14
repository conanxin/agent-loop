---
title: agent-loop Protocol Specification
version: 1.0
author: agent-loop OSS
---

# SPEC.md — agent-loop Protocol Specification

## Overview

agent-loop is a **file-based relay protocol** for dual-agent collaboration between OpenClaw (planning/judging) and Hermes (execution/reporting). All structured communication is written to the filesystem; Telegram carries only lightweight 2-line status notifications.

## Directory Structure

```
~/.agent-loop/
├── goals/
│   └── <goal-id>/
│       ├── state.json          # State machine + metadata
│       ├── hermes-commands/
│       │   └── <iteration>.md   # BEGIN_HERMES_COMMAND blocks
│       ├── hermes-reports/
│       │   └── <iteration>.md   # BEGIN_HERMES_REPORT blocks
│       ├── openclaw-decisions/
│       │   └── <iteration>.md   # BEGIN_OPENCLAW_DECISION blocks
│       └── artifacts/
│           └── detail.md         # Free-form detail artifacts
├── bin/
│   ├── agent-loop-init-goal
│   ├── agent-loop-set-state
│   ├── agent-loop-show
│   └── agent-loop-relay
└── README.md
```

## Protocol Blocks

### BEGIN_HERMES_COMMAND

Sent by OpenClaw to Hermes. Contains the task to execute.

**Required fields:**
- `goal_id`: Goal identifier
- `iteration`: Command iteration number
- `command_type`: `implement` | `validate` | `document`
- `objective`: One-line task description
- `instructions`: Numbered execution steps
- `validation`: Success criteria
- `report_back`: Expected report format
- `stop_conditions`: Failure conditions

**Optional fields:**
- `context`: Background information
- `working_directory`: Execution directory

### BEGIN_HERMES_REPORT

Sent by Hermes to OpenClaw. Contains execution results.

**Required fields (11):**
- `goal_id`
- `iteration`
- `status`: `PASS` | `PARTIAL` | `FAIL` | `BLOCKED`
- `summary`: One-line result
- `changed_files`: List or `none`
- `commands_run`: List of commands executed
- `validation_result`: Structured validation output
- `commit`: Git SHA or `none`
- `report_path`: Absolute path to this report
- `issues`: List or `none`
- `recommendation`: Next step suggestion

### BEGIN_OPENCLAW_DECISION

Sent by OpenClaw after judging. Contains the final decision.

**Required fields (6):**
- `goal_id`
- `iteration`
- `decision`: `DONE` | `NEXT_COMMAND` | `REPAIR_COMMAND` | `PARTIAL` | `BLOCKED` | `NEEDS_HUMAN_REVIEW`
- `requires_human_approval`: `true` | `false`
- `reason`: Explanation
- `next_expected_result`: What Hermes should do next

## State Machine

| State | Description | Next Action |
|---|---|---|
| `INIT` | Goal created | Set to `COMMAND_READY` |
| `OPENCLAW_PLANNING` | OpenClaw planning next command | Wait for command file |
| `COMMAND_READY` | Command written, ready to dispatch | `relay --once` prints command |
| `DISPATCHED_TO_HERMES` | Command sent to Hermes | Hermes executes |
| `HERMES_RUNNING` | Hermes executing | Wait for report |
| `HERMES_REPORT_WRITTEN` | Report written | `--report-path` to record |
| `OPENCLAW_JUDGING` | OpenClaw judging | `--judge-prompt` to build prompt |
| `DONE` | Goal complete | No further action |
| `PARTIAL` | Partial success | Human review needed |
| `BLOCKED` | Blocked | Human intervention needed |
| `NEEDS_HUMAN_REVIEW` | Needs human review | Human decides next step |

## Telegram Transport

**Allowed messages (exactly 2 lines):**

```
HERMES_STATUS: REPORT_WRITTEN
HERMES_REPORT_PATH: <absolute-path>
```

**Why not Telegram for structured data:**
- Token limits truncate long reports
- Format drift (Markdown rendering varies by client)
- No guaranteed delivery or ordering
- Difficult to version control

## Tools

### agent-loop-init-goal

Create a new goal directory with initial state.

```bash
agent-loop-init-goal <goal-id> "<description>"
```

### agent-loop-set-state

Manually set goal state.

```bash
agent-loop-set-state <goal-id> <state>
```

### agent-loop-show

Display goal state and recent files.

```bash
agent-loop-show <goal-id>
```

### agent-loop-relay

State machine relay with multiple modes:

```bash
# Print current command without advancing
agent-loop-relay --once <goal-id>

# Mark as dispatched (advance to DISPATCHED_TO_HERMES)
agent-loop-relay --once <goal-id> --mark-dispatched

# Record report path (advance to HERMES_REPORT_WRITTEN)
agent-loop-relay --once <goal-id> --report-path <path>

# Build judge prompt (only in HERMES_REPORT_WRITTEN)
agent-loop-relay --judge-prompt <goal-id>

# Mark as judging (advance to OPENCLAW_JUDGING)
agent-loop-relay --judge-prompt <goal-id> --mark-judging

# Ingest decision file (advance to final state)
agent-loop-relay --decision-path <goal-id> <decision-file>
```

## Safety Boundaries

1. **No auto-execution**: relay prints commands; human copies them
2. **No real project modification without approval**: validation tasks use `make validate` (read-only)
3. **No token leakage**: All secrets stay in `.env` (gitignored)
4. **No path leakage**: Use `~/.agent-loop` instead of absolute home paths in docs
5. **State machine enforcement**: `--decision-path` only valid in `OPENCLAW_JUDGING` or `HERMES_REPORT_WRITTEN`

## Version History

- v1.0.0 (2024-06-14): Initial OSS release with manual relay mode
