---
title: Manual Relay Smoke Test Example
---

# Manual Relay Smoke Test Example

This is a fictional smoke test matching the Phase 5D workflow, but with entirely fake data.

## Goal Information

| Field | Value |
|---|---|
| goal_id | smoke-test-demo-2024 |
| description | Demo smoke test for manual relay workflow |
| created | 2024-06-14T00:00:00Z |

## State Transition Log

| Step | Action | State Before | State After |
|---|---|---|---|
| 1 | `init-goal` | - | INIT |
| 2 | `set-state COMMAND_READY` | INIT | COMMAND_READY |
| 3 | Write command file | COMMAND_READY | COMMAND_READY |
| 4 | `relay --once` | COMMAND_READY | COMMAND_READY (printed) |
| 5 | `relay --once --mark-dispatched` | COMMAND_READY | DISPATCHED_TO_HERMES |
| 6 | Hermes executes | DISPATCHED_TO_HERMES | HERMES_REPORT_WRITTEN (after --report-path) |
| 7 | `relay --once --report-path` | DISPATCHED_TO_HERMES | HERMES_REPORT_WRITTEN |
| 8 | `relay --judge-prompt` | HERMES_REPORT_WRITTEN | HERMES_REPORT_WRITTEN (printed) |
| 9 | `relay --judge-prompt --mark-judging` | HERMES_REPORT_WRITTEN | OPENCLAW_JUDGING |
| 10 | OpenClaw writes decision | OPENCLAW_JUDGING | OPENCLAW_JUDGING |
| 11 | `relay --decision-path` | OPENCLAW_JUDGING | DONE |
| 12 | `show` | DONE | DONE (verified) |

## Command File (hermes-commands/001.md)

```markdown
BEGIN_HERMES_COMMAND
goal_id: smoke-test-demo-2024
iteration: 1
command_type: implement
objective: Create a demo artifact for smoke test
context: This is a fictional smoke test with no real project impact
working_directory: /tmp
instructions:
  1. Create a temporary file with demo content
  2. Verify the file exists
validation: File exists and contains expected content
report_back: HERMES_STATUS: REPORT_WRITTEN
stop_conditions: If file creation fails, report FAIL
END_HERMES_COMMAND
```

## Report File (hermes-reports/001.md)

```markdown
BEGIN_HERMES_REPORT
goal_id: smoke-test-demo-2024
iteration: 1
status: PASS
summary: Demo smoke test completed successfully
changed_files: none
commands_run: - echo "demo" > /tmp/demo.txt
validation_result: File created and verified
commit: none
report_path: ~/.agent-loop/goals/smoke-test-demo-2024/hermes-reports/001.md
issues: none
recommendation: This is a fictional example for documentation
END_HERMES_REPORT
```

## Decision File (openclaw-decisions/001.md)

```markdown
BEGIN_OPENCLAW_DECISION
goal_id: smoke-test-demo-2024
iteration: 1
decision: DONE
requires_human_approval: false
reason: Demo smoke test passed all checks
next_expected_result: No further action needed
END_OPENCLAW_DECISION
```

## Artifact (artifacts/detail.md)

This smoke test demonstrates the complete manual relay workflow:

1. **Initialization**: Goal created with `agent-loop-init-goal`
2. **Command Preparation**: Dummy command written to `hermes-commands/001.md`
3. **Dispatch**: Command printed by `relay --once`, human confirms with `--mark-dispatched`
4. **Execution**: Hermes executes the command (fictional in this example)
5. **Report**: Hermes writes report, human records with `--report-path`
6. **Judge**: OpenClaw judges the report, human triggers with `--mark-judging`
7. **Decision**: OpenClaw writes decision, human ingests with `--decision-path`
8. **Completion**: State reaches `DONE`

## Safety Notes

- All data in this example is fictional
- No real project files were modified
- No actual commands were executed
- This is for documentation purposes only
