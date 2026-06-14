# agent-loop

[![CI](https://github.com/conanxin/agent-loop/actions/workflows/ci.yml/badge.svg)](https://github.com/conanxin/agent-loop/actions/workflows/ci.yml)

[中文说明 / Chinese Guide](README.zh-CN.md)

OpenClaw ↔️ Hermes dual-agent file-based relay loop protocol.

## Quick Install

### Skills Quick Install

```bash
./scripts/install-all.sh
```

Install Skills only:

```bash
./scripts/install-skills.sh
```

### Full Install

```bash
git clone https://github.com/conanxin/agent-loop.git
cd agent-loop
./scripts/install-all.sh
export PATH="$HOME/.agent-loop/bin:$PATH"
```

For custom paths or step-by-step install, see [docs/INSTALL.md](docs/INSTALL.md).

## Why agent-loop?

When two AI agents (OpenClaw for planning/judging, Hermes for execution/reporting) collaborate, they need a reliable communication channel. Telegram is convenient but has critical limitations:

- **Token limits** truncate long reports
- **Format drift** — Markdown rendering varies by client
- **No guaranteed delivery** or ordering
- **Difficult to version control** or audit

**agent-loop** solves this by moving all structured communication to the filesystem. Telegram carries only 2-line status notifications:

```
HERMES_STATUS: REPORT_WRITTEN
HERMES_REPORT_PATH: ~/.agent-loop/goals/my-project/hermes-reports/001.md
```

## Architecture

```
┌─────────────┐      ┌─────────────┐      ┌─────────────┐
│   OpenClaw  │◄────►│  Filesystem │◄────►│   Hermes    │
│  (Planner)  │      │  (Relay)    │      │ (Executor)  │
└─────────────┘      └─────────────┘      └─────────────┘
       │                     │                    │
       │              ┌──────┴──────┐            │
       │              │   Telegram  │            │
       │              │  (2 lines)  │            │
       │              └─────────────┘            │
       │                                         │
       ▼                                         ▼
openclaw-decisions/                      hermes-commands/
hermes-reports/                          hermes-reports/
```

## Install

```bash
git clone https://github.com/conanxin/agent-loop.git
cd agent-loop
./scripts/install.sh
```

Or use the full installer (tools + skills + smoke test):

```bash
./scripts/install-all.sh
```

For custom paths or advanced options, see [docs/INSTALL.md](docs/INSTALL.md).

## Directory Structure

```
~/.agent-loop/
├── goals/
│   └── <goal-id>/
│       ├── state.json
│       ├── hermes-commands/
│       ├── hermes-reports/
│       ├── openclaw-decisions/
│       └── artifacts/
├── bin/
│   ├── agent-loop-init-goal
│   ├── agent-loop-set-state
│   ├── agent-loop-show
│   └── agent-loop-relay
└── README.md
```

## Quick Start

### 1. Initialize a goal

```bash
agent-loop-init-goal my-project "Implement feature X"
```

### 2. Set state to ready

```bash
agent-loop-set-state my-project COMMAND_READY
```

### 3. Write a command

Create `~/.agent-loop/goals/my-project/hermes-commands/001.md`:

```markdown
BEGIN_HERMES_COMMAND
goal_id: my-project
iteration: 1
command_type: implement
objective: Implement feature X
instructions:
  1. Run tests
  2. Implement the feature
  3. Verify with make validate
validation: Tests pass, make validate returns 0
report_back: HERMES_STATUS: REPORT_WRITTEN
stop_conditions: If tests fail, report FAIL
END_HERMES_COMMAND
```

### 4. Print the command

```bash
agent-loop-relay --once my-project
```

Copy the printed command to Hermes.

### 5. Mark as dispatched

```bash
agent-loop-relay --once my-project --mark-dispatched
```

### 6. Record the report

After Hermes executes and writes the report:

```bash
agent-loop-relay --once my-project --report-path ~/.agent-loop/goals/my-project/hermes-reports/001.md
```

### 7. Build judge prompt

```bash
agent-loop-relay --judge-prompt my-project
```

Copy the prompt to OpenClaw.

### 8. Mark as judging

```bash
agent-loop-relay --judge-prompt my-project --mark-judging
```

### 9. Ingest decision

After OpenClaw writes the decision:

```bash
agent-loop-relay --decision-path my-project ~/.agent-loop/goals/my-project/openclaw-decisions/001.md
```

## Command Reference

| Command | Description |
|---|---|
| `agent-loop-init-goal <id> "desc"` | Create a new goal |
| `agent-loop-set-state <id> <state>` | Manually set state |
| `agent-loop-show <id>` | Display goal state |
| `agent-loop-relay --once <id>` | Print command (no advance) |
| `agent-loop-relay --once <id> --mark-dispatched` | Advance to DISPATCHED_TO_HERMES |
| `agent-loop-relay --once <id> --report-path <path>` | Record report, advance to HERMES_REPORT_WRITTEN |
| `agent-loop-relay --judge-prompt <id>` | Build judge prompt |
| `agent-loop-relay --judge-prompt <id> --mark-judging` | Advance to OPENCLAW_JUDGING |
| `agent-loop-relay --decision-path <id> <file>` | Ingest decision, advance to final state |

## State Machine

```
INIT → COMMAND_READY → DISPATCHED_TO_HERMES → HERMES_REPORT_WRITTEN → OPENCLAW_JUDGING → DONE
```

See [docs/STATE_MACHINE.md](docs/STATE_MACHINE.md) for full diagram.

## Protocol

### BEGIN_HERMES_COMMAND

Sent by OpenClaw to Hermes. Contains the task to execute.

### BEGIN_HERMES_REPORT

Sent by Hermes to OpenClaw. Contains execution results.

### BEGIN_OPENCLAW_DECISION

Sent by OpenClaw after judging. Contains the final decision.

See [docs/SCHEMAS.md](docs/SCHEMAS.md) for full schema documentation.

## Safety

- **No auto-execution**: relay prints commands; human confirms
- **No real project modification without approval**: validation uses `make validate` (read-only)
- **No token leakage**: secrets in `.env` (gitignored)
- **No path leakage**: use `~/.agent-loop` instead of absolute paths

See [docs/SAFETY_BOUNDARIES.md](docs/SAFETY_BOUNDARIES.md) for full safety rules.

## Skills

Install both OpenClaw and Hermes skills:

```bash
./scripts/install-skills.sh
```

This installs:
- OpenClaw skill: `hermes-agent-loop` → `~/.openclaw/workspace/skills/`
- Hermes skill: `openclaw-command-executor` → `~/.hermes/skills/`

For custom paths, set `OPENCLAW_SKILLS_DIR` or `HERMES_SKILLS_DIR` before running.

See [docs/AGENT_SKILLS.md](docs/AGENT_SKILLS.md) for detailed usage.

## For Agents

If you are an agent reading this, here's the fastest path to get started:

```bash
# 1. Install everything
./scripts/install-all.sh

# 2. Update PATH
export PATH="$HOME/.agent-loop/bin:$PATH"

# 3. Verify skills are installed
ls -la ${OPENCLAW_SKILLS_DIR:-$HOME/.openclaw/workspace/skills}/hermes-agent-loop/
ls -la ${HERMES_SKILLS_DIR:-$HOME/.hermes/skills}/openclaw-command-executor/

# 4. Create a test goal
agent-loop-init-goal test "Test goal"
agent-loop-set-state test COMMAND_READY
agent-loop-show test
```

## Continuous Integration

The repository has a GitHub Actions workflow at `.github/workflows/ci.yml` that runs on every push/PR to main. It enforces:

- `bash -n` on all scripts and bin tools
- `scripts/validate-skills.sh` for skill content validation
- `make validate` for project structure and secret scanning
- `scripts/smoke-test.sh` end-to-end test in an isolated `AGENT_LOOP_HOME`

The CI badge at the top of this README reflects the current build status.

Run the same checks locally:

```bash
chmod +x scripts/*.sh bin/agent-loop-*
make validate
./scripts/validate-skills.sh
AGENT_LOOP_HOME=/tmp/agent-loop-smoke ./scripts/smoke-test.sh
```

## Documentation

- [SPEC.md](docs/SPEC.md) — Protocol specification
- [STATE_MACHINE.md](docs/STATE_MACHINE.md) — State machine documentation
- [MANUAL_RELAY_WORKFLOW.md](docs/MANUAL_RELAY_WORKFLOW.md) — Step-by-step guide
- [SCHEMAS.md](docs/SCHEMAS.md) — Protocol schemas
- [SAFETY_BOUNDARIES.md](docs/SAFETY_BOUNDARIES.md) — Safety rules
- [TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) — Common issues
- [AGENT_SKILLS.md](docs/AGENT_SKILLS.md) — OpenClaw/Hermes skills
- [SKILL_DESIGN.zh-CN.md](docs/SKILL_DESIGN.zh-CN.md) — Skill design (zh-CN)
- [AGENT_ROLES.zh-CN.md](docs/AGENT_ROLES.zh-CN.md) — Agent roles (zh-CN)

## Common Protocol Drift Issues

| Issue | Cause | Fix |
|---|---|---|
| Old notification format (`REPORT_WRITTEN\n/path`) | Used shorthand instead of key:value | Use `HERMES_STATUS: REPORT_WRITTEN` + `HERMES_REPORT_PATH: <path>` |
| Markdown report instead of canonical | Hermes writes `# Report` instead of `BEGIN_HERMES_REPORT` block | Use strict 11-field `BEGIN_HERMES_REPORT` format |
| Scope expansion (`make validate` → `make test`) | Hermes runs additional commands | Stop after requested command passes |
| Multiple `BEGIN_HERMES_COMMAND` blocks | OpenClaw plan mode emits inspect + implement | Output exactly one main command block |
| Wrong judge prompt format | Inline path instead of separate line | Use `/skill hermes-agent-loop judge-path` + `report_path: <path>` on separate lines |

## Examples

- [examples/minimal-goal/](examples/minimal-goal/) — Minimal goal with fictional data
- [examples/manual-relay-smoke-test/](examples/manual-relay-smoke-test/) — Complete smoke test walkthrough

## Scripts

- [scripts/install.sh](scripts/install.sh) — Installation script
- [scripts/smoke-test.sh](scripts/smoke-test.sh) — End-to-end smoke test

## License

MIT License — see [LICENSE](LICENSE)

## Changelog

See [CHANGELOG.md](CHANGELOG.md)
