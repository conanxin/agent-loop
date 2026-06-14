---
title: Protocol Schemas
version: 1.0
---

# SCHEMAS.md

## BEGIN_OPENCLAW_DECISION

```yaml
BEGIN_OPENCLAW_DECISION
goal_id: <string>                    # Required. Must match the goal directory name
iteration: <integer>                 # Required. Sequential iteration number
decision: <enum>                     # Required. One of:
                                     #   - DONE
                                     #   - NEXT_COMMAND
                                     #   - REPAIR_COMMAND
                                     #   - PARTIAL
                                     #   - BLOCKED
                                     #   - NEEDS_HUMAN_REVIEW
requires_human_approval: <boolean>   # Required. true or false
reason: <string>                     # Required. Human-readable explanation
next_expected_result: <string>       # Required. What Hermes should do next
END_OPENCLAW_DECISION
```

**Validation Rules:**
- All 6 fields are mandatory
- `goal_id` must match the goal directory name
- `decision` must be one of the 6 enum values
- `iteration` must be a positive integer
- `requires_human_approval` must be exactly `true` or `false`
- Empty values are rejected

## BEGIN_HERMES_COMMAND

```yaml
BEGIN_HERMES_COMMAND
goal_id: <string>                    # Required. Goal identifier
iteration: <integer>                 # Required. Command iteration number
command_type: <enum>                 # Required. One of: implement, validate, document
objective: <string>                  # Required. One-line task description
context: <string>                    # Optional. Background information
working_directory: <path>           # Optional. Execution directory
instructions:                         # Required. Numbered execution steps
  1. <step>
  2. <step>
validation: <string>                 # Required. Success criteria
report_back: <string>                # Required. Expected report format
stop_conditions: <string>             # Required. Failure conditions
END_HERMES_COMMAND
```

**Validation Rules:**
- `goal_id`, `iteration`, `command_type`, `objective`, `instructions`, `validation`, `report_back`, `stop_conditions` are mandatory
- `command_type` must be one of: `implement`, `validate`, `document`
- `instructions` must be a numbered list

## BEGIN_HERMES_REPORT

```yaml
BEGIN_HERMES_REPORT
goal_id: <string>                    # Required. Goal identifier
iteration: <integer>                 # Required. Report iteration number
status: <enum>                       # Required. One of: PASS, PARTIAL, FAIL, BLOCKED
summary: <string>                    # Required. One-line result
changed_files: <string>              # Required. List of changed files or "none"
commands_run: <string>              # Required. List of commands executed
validation_result: <string>          # Required. Structured validation output
commit: <string>                     # Required. Git SHA or "none"
report_path: <string>               # Required. Absolute path to this report
issues: <string>                     # Required. List of issues or "none"
recommendation: <string>             # Required. Next step suggestion
END_HERMES_REPORT
```

**Validation Rules:**
- All 11 fields are mandatory
- `status` must be one of: `PASS`, `PARTIAL`, `FAIL`, `BLOCKED`
- `report_path` must be an absolute path
- `commit` must be a valid SHA or `none`
- Empty values are rejected for critical fields

## State Machine States

```yaml
INIT:                  # Goal created, no command yet
OPENCLAW_PLANNING:     # OpenClaw planning next command
COMMAND_READY:         # Command written, ready to dispatch
DISPATCHED_TO_HERMES:  # Command sent to Hermes
HERMES_RUNNING:        # Hermes executing
HERMES_REPORT_WRITTEN: # Report written
OPENCLAW_JUDGING:      # OpenClaw judging
DONE:                  # Goal complete
PARTIAL:               # Partial success
BLOCKED:               # Blocked
NEEDS_HUMAN_REVIEW:    # Needs human review
```

## File Naming Conventions

| File Type | Pattern | Example |
|---|---|---|
| Command | `hermes-commands/<iteration>.md` | `hermes-commands/001.md` |
| Report | `hermes-reports/<iteration>.md` | `hermes-reports/001.md` |
| Decision | `openclaw-decisions/<iteration>.md` | `openclaw-decisions/001.md` |
| Artifact | `artifacts/<name>.md` | `artifacts/detail.md` |
| State | `state.json` | `state.json` |

## JSON Schema for state.json

```json
{
  "goal_id": "string",
  "current_state": "enum",
  "iteration": "integer",
  "last_command": "string|null",
  "last_report": "string|null",
  "last_decision": "string|null",
  "human_approval_required": "boolean",
  "human_approved": "boolean|null",
  "created_at": "ISO8601",
  "updated_at": "ISO8601"
}
```

## Decision to State Mapping

| Decision | New State | Description |
|---|---|---|
| DONE | DONE | Loop complete |
| NEXT_COMMAND | OPENCLAW_PLANNING | Plan next command |
| REPAIR_COMMAND | OPENCLAW_PLANNING | Repair current command |
| PARTIAL | PARTIAL | Partial success |
| BLOCKED | BLOCKED | Blocked |
| NEEDS_HUMAN_REVIEW | NEEDS_HUMAN_REVIEW | Needs review |
