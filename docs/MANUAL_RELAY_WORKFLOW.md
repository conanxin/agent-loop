---
title: Manual Relay Workflow Guide
version: 1.0
---

# MANUAL_RELAY_WORKFLOW.md

## Overview

The **manual relay** mode is the default and safest way to use agent-loop. It requires human confirmation at every state transition, preventing accidental execution or data loss.

## Why Manual?

- **Safety**: No command auto-executes
- **Transparency**: You see every command before it runs
- **Control**: You decide when to advance the state machine
- **Auditability**: Every step is logged in state.json

## Prerequisites

```bash
# Install agent-loop
git clone https://github.com/conanxin/agent-loop.git
cd agent-loop
./scripts/install.sh

# Verify installation
agent-loop-init-goal test "Test installation"
agent-loop-show test
```

## Step-by-Step Workflow

### Step 1: Initialize Goal

```bash
agent-loop-init-goal my-project "Implement feature X"
```

Creates:
```
~/.agent-loop/goals/my-project/
├── state.json          # { "current_state": "INIT", ... }
├── hermes-commands/
├── hermes-reports/
├── openclaw-decisions/
└── artifacts/
```

### Step 2: Set State to COMMAND_READY

```bash
agent-loop-set-state my-project COMMAND_READY
```

### Step 3: Write Command File

Create `~/.agent-loop/goals/my-project/hermes-commands/001.md`:

```markdown
BEGIN_HERMES_COMMAND
goal_id: my-project
iteration: 1
command_type: implement
objective: Implement feature X
context: This is a demo project
working_directory: ~/projects/my-project
instructions:
  1. Run tests
  2. Implement feature
  3. Verify with make validate
validation: Tests pass, make validate returns 0
report_back: HERMES_STATUS: REPORT_WRITTEN
stop_conditions: If tests fail, report FAIL
END_HERMES_COMMAND
```

### Step 4: Print Command (No Auto-Advance)

```bash
agent-loop-relay --once my-project
```

Output:
```
=== Hermes Command for my-project ===
BEGIN_HERMES_COMMAND
...
END_HERMES_COMMAND
=== End of Command ===

human_approval_required=false. State stays at COMMAND_READY.
Please copy the above command to Hermes.
After copying, run:
  agent-loop-relay --once my-project --mark-dispatched
```

**Important**: The state stays at `COMMAND_READY`. Nothing executes automatically.

### Step 5: Mark Dispatched

After you copy the command to Hermes:

```bash
agent-loop-relay --once my-project --mark-dispatched
```

Output:
```
state: COMMAND_READY -> DISPATCHED_TO_HERMES
Dispatched (user confirmed). Waiting for Hermes to return:
HERMES_STATUS: REPORT_WRITTEN
HERMES_REPORT_PATH: ~/.agent-loop/goals/my-project/hermes-reports/001.md
```

### Step 6: Hermes Executes and Returns Report

Hermes will:
1. Execute the command
2. Write a canonical report to `hermes-reports/001.md`
3. Send Telegram notification:
   ```
   HERMES_STATUS: REPORT_WRITTEN
   HERMES_REPORT_PATH: ~/.agent-loop/goals/my-project/hermes-reports/001.md
   ```

### Step 7: Record Report Path

```bash
agent-loop-relay --once my-project --report-path ~/.agent-loop/goals/my-project/hermes-reports/001.md
```

Output:
```
state: DISPATCHED_TO_HERMES -> HERMES_REPORT_WRITTEN
Report received: ~/.agent-loop/goals/my-project/hermes-reports/001.md
Next: Run 'agent-loop-relay --judge-prompt my-project' to build the judge prompt for OpenClaw.
```

### Step 8: Build Judge Prompt

```bash
agent-loop-relay --judge-prompt my-project
```

Output:
```
=== Judge Prompt for OpenClaw ===
/skill hermes-agent-loop judge-path

report_path: ~/.agent-loop/goals/my-project/hermes-reports/001.md

要求：
1. 使用绝对路径读取 canonical report。
2. 严格检查 BEGIN_HERMES_REPORT 15 点格式。
3. 根据 status 判断 DONE / PARTIAL / REPAIR_COMMAND / BLOCKED / NEEDS_HUMAN_REVIEW。
4. 如果判断完成，请输出 BEGIN_OPENCLAW_DECISION。
5. 不从 Telegram 文本解析报告正文。
=== End of Judge Prompt ===

Please copy the above prompt to OpenClaw bot.
State not changed. Use --mark-judging to advance state.
```

### Step 9: Mark Judging

After you copy the prompt to OpenClaw:

```bash
agent-loop-relay --judge-prompt my-project --mark-judging
```

Output:
```
state: HERMES_REPORT_WRITTEN -> OPENCLAW_JUDGING
State updated to OPENCLAW_JUDGING.
```

### Step 10: OpenClaw Judges and Writes Decision

OpenClaw will:
1. Read the canonical report
2. Judge the results
3. Write a decision file to `openclaw-decisions/001.md`

Example decision:
```markdown
BEGIN_OPENCLAW_DECISION
goal_id: my-project
iteration: 1
decision: DONE
requires_human_approval: false
reason: All tests pass, feature implemented correctly
next_expected_result: No further action needed
END_OPENCLAW_DECISION
```

### Step 11: Ingest Decision

```bash
agent-loop-relay --decision-path my-project ~/.agent-loop/goals/my-project/openclaw-decisions/001.md
```

Output:
```
Decision ingested: DONE for my-project
State updated: OPENCLAW_JUDGING -> DONE
Last decision: ~/.agent-loop/goals/my-project/openclaw-decisions/001.md
Goal my-project is complete. No further action needed.
```

### Step 12: Verify Final State

```bash
agent-loop-show my-project
```

Output:
```
goal_id:                   my-project
current_state:             DONE
last_command:              ~/.agent-loop/goals/my-project/hermes-commands/001.md
last_report:               ~/.agent-loop/goals/my-project/hermes-reports/001.md
last_decision:             ~/.agent-loop/goals/my-project/openclaw-decisions/001.md
```

## Complete Loop Summary

| Step | Action | State After |
|---|---|---|
| 1 | `init-goal` | INIT |
| 2 | `set-state COMMAND_READY` | COMMAND_READY |
| 3 | Write command file | COMMAND_READY |
| 4 | `relay --once` | COMMAND_READY (printed) |
| 5 | `relay --once --mark-dispatched` | DISPATCHED_TO_HERMES |
| 6 | Hermes executes | HERMES_REPORT_WRITTEN (after --report-path) |
| 7 | `relay --once --report-path` | HERMES_REPORT_WRITTEN |
| 8 | `relay --judge-prompt` | HERMES_REPORT_WRITTEN (printed) |
| 9 | `relay --judge-prompt --mark-judging` | OPENCLAW_JUDGING |
| 10 | OpenClaw writes decision | OPENCLAW_JUDGING |
| 11 | `relay --decision-path` | DONE |
| 12 | `show` | DONE (verified) |

## Safety Checkpoints

- **Checkpoint 1**: Before `--mark-dispatched` — review the command
- **Checkpoint 2**: Before `--report-path` — verify the report exists
- **Checkpoint 3**: Before `--mark-judging` — review the judge prompt
- **Checkpoint 4**: Before `--decision-path` — review the decision file

## Common Mistakes

1. **Forgetting `--mark-dispatched`**: State stays at COMMAND_READY
2. **Wrong report path**: Use absolute path, not relative
3. **Missing decision fields**: Must include all 6 required fields
4. **Wrong state for `--decision-path`**: Only valid in OPENCLAW_JUDGING or HERMES_REPORT_WRITTEN

## Troubleshooting

See [TROUBLESHOOTING.md](TROUBLESHOOTING.md) for common issues.
