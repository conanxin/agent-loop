---
title: State Machine Documentation
version: 1.0
---

# STATE_MACHINE.md

## Complete State Diagram

```
                    ┌─────────────┐
                    │    INIT     │
                    └──────┬──────┘
                           │ init-goal
                           ▼
              ┌────────────────────────┐
              │   OPENCLAW_PLANNING    │◄─────────────────────────┐
              └───────────┬────────────┘                          │
                          │ OpenClaw writes command                 │
                          ▼                                         │
              ┌────────────────────────┐                            │
              │     COMMAND_READY      │                            │
              └───────────┬────────────┘                            │
                          │ relay --once (prints, no advance)        │
                          │ user copies command to Hermes           │
                          ▼                                         │
              ┌────────────────────────┐                            │
              │  DISPATCHED_TO_HERMES  │                            │
              └───────────┬────────────┘                            │
                          │ Hermes executes                         │
                          │ writes report                           │
                          ▼                                         │
              ┌────────────────────────┐                            │
              │   HERMES_REPORT_WRITTEN  │                            │
              └───────────┬────────────┘                            │
                          │ relay --judge-prompt                    │
                          │ user copies prompt to OpenClaw          │
                          ▼                                         │
              ┌────────────────────────┐                            │
              │    OPENCLAW_JUDGING    │                            │
              └───────────┬────────────┘                            │
                          │ OpenClaw writes decision                │
                          │ relay --decision-path                   │
                          ▼                                         │
        ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐         │
        │  DONE   │  │ PARTIAL │  │ BLOCKED │  │ NEEDS_  │         │
        │         │  │         │  │         │  │ HUMAN_  │         │
        └─────────┘  └─────────┘  └─────────┘  │ REVIEW  │         │
                                                 └────┬────┘         │
                                                      │              │
                    ┌─────────────────────────────────┘              │
                    │ decision = NEXT_COMMAND/REPAIR_COMMAND          │
                    └─────────────────────────────────────────────────┘
```

## State Descriptions

| State | Actor | Description |
|---|---|---|
| `INIT` | System | Goal directory created, no command yet |
| `OPENCLAW_PLANNING` | OpenClaw | OpenClaw is planning the next command |
| `COMMAND_READY` | System | Command file written, waiting for dispatch |
| `DISPATCHED_TO_HERMES` | Human | Human confirmed command sent to Hermes |
| `HERMES_RUNNING` | Hermes | Hermes is executing the command |
| `HERMES_REPORT_WRITTEN` | Hermes | Hermes wrote the canonical report |
| `OPENCLAW_JUDGING` | OpenClaw | OpenClaw is judging the report |
| `DONE` | System | Goal complete, loop closed |
| `PARTIAL` | System | Partial success, needs follow-up |
| `BLOCKED` | System | Blocked, needs human intervention |
| `NEEDS_HUMAN_REVIEW` | System | Needs human review before continuing |

## Transitions

| From | To | Trigger | Command |
|---|---|---|---|
| `INIT` | `COMMAND_READY` | Manual | `agent-loop-set-state` |
| `COMMAND_READY` | `DISPATCHED_TO_HERMES` | Human confirmation | `relay --once --mark-dispatched` |
| `DISPATCHED_TO_HERMES` | `HERMES_REPORT_WRITTEN` | Hermes report | `relay --once --report-path` |
| `HERMES_REPORT_WRITTEN` | `OPENCLAW_JUDGING` | Human confirmation | `relay --judge-prompt --mark-judging` |
| `OPENCLAW_JUDGING` | `DONE` | OpenClaw decision | `relay --decision-path` (DONE) |
| `OPENCLAW_JUDGING` | `OPENCLAW_PLANNING` | OpenClaw decision | `relay --decision-path` (NEXT_COMMAND) |
| `OPENCLAW_JUDGING` | `PARTIAL` | OpenClaw decision | `relay --decision-path` (PARTIAL) |
| `OPENCLAW_JUDGING` | `BLOCKED` | OpenClaw decision | `relay --decision-path` (BLOCKED) |
| `OPENCLAW_JUDGING` | `NEEDS_HUMAN_REVIEW` | OpenClaw decision | `relay --decision-path` (NEEDS_HUMAN_REVIEW) |

## Decision → State Mapping

| Decision | Resulting State | Next Action |
|---|---|---|
| `DONE` | `DONE` | Loop complete |
| `NEXT_COMMAND` | `OPENCLAW_PLANNING` | OpenClaw plans next command |
| `REPAIR_COMMAND` | `OPENCLAW_PLANNING` | OpenClaw repairs current command |
| `PARTIAL` | `PARTIAL` | Human reviews partial results |
| `BLOCKED` | `BLOCKED` | Human unblocks |
| `NEEDS_HUMAN_REVIEW` | `NEEDS_HUMAN_REVIEW` | Human reviews and decides |

## Error States

- `BLOCKED`: Unrecoverable error, human must intervene
- `PARTIAL`: Recoverable but incomplete, human decides retry or accept
- `NEEDS_HUMAN_REVIEW`: Ambiguous result, human must judge
