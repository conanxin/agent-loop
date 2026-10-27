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

## Implementation consistency notes (review this section as part of the specification)

- The following notes are normative parts of this draft and must be checked against the earlier specification.
- A reviewer may move directly from COMMAND_READY to OPENCLAW_JUDGING with relay --judge-prompt --mark-judging without a dispatch or report.
- Decision REPAIR_COMMAND always enters DONE because repairing a command is defined as a terminal decision.
- Decision PARTIAL enters PARTIAL and requires a human to decide the follow-up.
