---
title: Minimal Goal Example
---

# Minimal Goal Example

This is a complete minimal goal with fictional data.

## Directory Structure

```
my-first-goal/
├── state.json
├── hermes-commands/
│   └── 001.md
├── hermes-reports/
│   └── 001.md
├── openclaw-decisions/
│   └── 001.md
└── artifacts/
    └── detail.md
```

## state.json

```json
{
  "goal_id": "my-first-goal",
  "current_state": "DONE",
  "iteration": 1,
  "last_command": "~/.agent-loop/goals/my-first-goal/hermes-commands/001.md",
  "last_report": "~/.agent-loop/goals/my-first-goal/hermes-reports/001.md",
  "last_decision": "~/.agent-loop/goals/my-first-goal/openclaw-decisions/001.md",
  "human_approval_required": false,
  "human_approved": null,
  "created_at": "2024-06-14T00:00:00Z",
  "updated_at": "2024-06-14T00:00:00Z"
}
```

## hermes-commands/001.md

```markdown
BEGIN_HERMES_COMMAND
goal_id: my-first-goal
iteration: 1
command_type: validate
objective: Validate the minimal goal example
context: This is a fictional example for documentation
working_directory: ~/projects/example
instructions:
  1. Check directory structure
  2. Verify all files exist
validation: All files present and correctly formatted
report_back: HERMES_STATUS: REPORT_WRITTEN
stop_conditions: If any file is missing, report FAIL
END_HERMES_COMMAND
```

## hermes-reports/001.md

```markdown
BEGIN_HERMES_REPORT
goal_id: my-first-goal
iteration: 1
status: PASS
summary: Minimal goal example validated successfully
changed_files: none
commands_run: - ls -la
validation_result: All required files present
commit: none
report_path: ~/.agent-loop/goals/my-first-goal/hermes-reports/001.md
issues: none
recommendation: Use this as a template for new goals
END_HERMES_REPORT
```

## openclaw-decisions/001.md

```markdown
BEGIN_OPENCLAW_DECISION
goal_id: my-first-goal
iteration: 1
decision: DONE
requires_human_approval: false
reason: Example goal completed successfully
next_expected_result: No further action needed
END_OPENCLAW_DECISION
```

## artifacts/detail.md

This is a free-form detail artifact. It can contain any additional information, logs, or notes about the goal execution.
