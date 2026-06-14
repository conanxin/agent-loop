---
name: hermes-agent-loop
description: "Plan and judge a multi-turn Hermes execution loop without executing the target task."
user-invocable: true
---

# Hermes Agent Loop

Orchestrate OpenClaw ↔️ Hermes dual-agent collaboration. OpenClaw acts as Planner/Judge; Hermes acts as Executor. OpenClaw never executes the target task or modifies project code.

## Modes

Invoke with mode: `plan`, `judge`, `judge-path`, or `auto-spec`.

### 1. plan — Generate first Hermes command

**Rule**: OpenClaw is Planner/Judge, NEVER Executor. OpenClaw plans and judges; Hermes executes.

**Input:** User goal (plain text or structured). Optional: project path, constraints.

**Output:**
- `BEGIN_OPENCLAW_DECISION` block (decision = NEXT_COMMAND, iteration = 1)
- **EXACTLY ONE** main `BEGIN_HERMES_COMMAND` block with the first command

**Scope rule**: For multi-phase tasks, output ONLY the next immediate command. Do NOT output inspect + implement as two separate executable blocks. Do NOT output multiple command blocks in one response. If the task has multiple phases, plan them mentally but emit only the first phase's command. The next phase will be planned after the judge step.

**Human review**: The `requires_human_approval` field in the decision block is the human checkpoint. Do NOT include a second command block that could be accidentally executed.

**Anti-drift example — WRONG (multiple commands):**
```
BEGIN_OPENCLAW_DECISION
...
END_OPENCLAW_DECISION

BEGIN_HERMES_COMMAND
command_type: inspect
...
END_HERMES_COMMAND

BEGIN_HERMES_COMMAND
command_type: implement
...
END_HERMES_COMMAND
```

**Anti-drift example — RIGHT (single command):**
```
BEGIN_OPENCLAW_DECISION
...
END_OPENCLAW_DECISION

BEGIN_HERMES_COMMAND
command_type: inspect
...
END_HERMES_COMMAND
```

### 2. judge — Evaluate Hermes report from Telegram text and decide next step

**Input:** Previous `BEGIN_OPENCLAW_DECISION` + `BEGIN_HERMES_COMMAND` + `BEGIN_HERMES_REPORT` from Hermes (inline in Telegram).

**Output:**
- `BEGIN_OPENCLAW_DECISION` block with updated decision
- If continuing: `BEGIN_HERMES_COMMAND` block with next command
- If done/blocked: human review points only

**Limitation:** Hermes' Telegram transport layer may reformat the `BEGIN_HERMES_REPORT` block, dropping `goal_id:` keys, `BEGIN_HERMES_REPORT` delimiters, or merging fields. Use `judge-path` for strict compliance.

### 3. judge-path — Evaluate Hermes report from a file

**Input:** Hermes lightweight status message + `report_path` pointing to a file containing the full `BEGIN_HERMES_REPORT`.

**Output:**
- `BEGIN_OPENCLAW_DECISION` block with updated decision
- If continuing: `BEGIN_HERMES_COMMAND` block with next command
- If done/blocked: human review points only

**Why judge-path:**
Hermes' Telegram text transport has been proven to corrupt strict `BEGIN_HERMES_REPORT` formatting through 4 rounds of repair (Phase 2B–2D). File-based reading bypasses this entirely and guarantees exact byte-level fidelity.

**Hermes lightweight notification format (Telegram):**
```
HERMES_STATUS: REPORT_WRITTEN
HERMES_REPORT_PATH: <absolute-path-to-report.md>
```

**OpenClaw then reads `<absolute-path-to-report.md>`** and uses its content as the sole source of truth for `BEGIN_HERMES_REPORT`.

**judge-path strict validation checklist (15 format checks on the 11-field schema):**
1. File must exist at `report_path`. If not → `BLOCKED`.
2. First non-whitespace line must be `BEGIN_HERMES_REPORT`.
3. Must contain `goal_id:` with a value.
4. Must contain `iteration:` with a value.
5. Must contain `status:` with value `PASS` | `PARTIAL` | `FAIL` | `BLOCKED`.
6. Must contain `summary:` with a value.
7. Must contain `changed_files:` with a value.
8. Must contain `commands_run:` with a value.
9. Must contain `validation_result:` with a value.
10. Must contain `commit:` with a value.
11. Must contain `report_path:` with a value.
12. Must contain `issues:` with a value.
13. Must contain `recommendation:` with a value.
14. Last non-whitespace line must be `END_HERMES_REPORT`.
15. Each field must be on its own line as `key: value` (or `key: |` for multi-line YAML).

**Decision mapping based on strict validation:**
- Any field missing or malformed → `REPAIR_COMMAND` or `BLOCKED` (specify which fields failed).
- All fields present and `status: PASS` → evaluate goal completion → `DONE` or `NEXT_COMMAND`.
- All fields present and `status: PARTIAL` → `NEXT_COMMAND` or `REPAIR_COMMAND`.
- All fields present and `status: FAIL` → `REPAIR_COMMAND`.
- All fields present and `status: BLOCKED` → `BLOCKED`.

### 4. auto-spec — Generate protocol specification only

**Input:** None (or project type hint).

**Output:** Protocol specification document for future automated relay. No execution commands generated.

---

## Protocol: BEGIN_OPENCLAW_DECISION

```
BEGIN_OPENCLAW_DECISION
goal_id: <unique-goal-id>
iteration: <int>
decision: DONE | NEXT_COMMAND | REPAIR_COMMAND | NEEDS_HUMAN_REVIEW | BLOCKED
requires_human_approval: true | false
reason: <one-line rationale>
next_expected_result: <what success looks like for this step>
END_OPENCLAW_DECISION
```

**Decisions:**
- `DONE` — Goal achieved, no further action needed.
- `NEXT_COMMAND` — Proceed to next planned step.
- `REPAIR_COMMAND` — Previous step failed/partial; retry with fix instructions.
- `NEEDS_HUMAN_REVIEW` — Ambiguous result; human must decide.
- `BLOCKED` — External dependency, permission, or unknown blocker.

**requires_human_approval:**
- `true` for: destructive operations, security-sensitive changes, first-time commit to production branch, ambiguous results.
- `false` for: routine inspection, documentation, safe validation.

---

## Protocol: BEGIN_HERMES_COMMAND

```
BEGIN_HERMES_COMMAND
goal_id: <same-as-decision>
iteration: <same-as-decision>
command_type: inspect | implement | repair | validate | commit | document
objective: <one-line what Hermes should accomplish>
context: <relevant files, previous state, known issues>
working_directory: <absolute or relative path>
instructions: <numbered steps Hermes must follow>
validation: <how Hermes confirms success>
report_back: <what Hermes must include in report>
stop_conditions: <when to abort and report failure>
END_HERMES_COMMAND
```

**command_type:**
- `inspect` — Read code, run tests, check status. Non-destructive.
- `implement` — Write/modify code. Requires human approval by default.
- `repair` — Fix known failure. Requires human approval if touches production.
- `validate` — Run tests, linters, checks. Non-destructive.
- `commit` — Git commit. Requires human approval.
- `document` — Update docs, README, comments. Generally safe.

---

## Protocol: BEGIN_HERMES_REPORT

Hermes must return reports in this exact format:

```
BEGIN_HERMES_REPORT
goal_id: <same-as-command>
iteration: <same-as-command>
status: PASS | PARTIAL | FAIL | BLOCKED
summary: <one-line outcome>
changed_files: <list of modified/created files, or "none">
commands_run: <list of commands executed>
validation_result: <test/lint output, or "not run">
commit: <commit hash or "none">
report_path: <path to detailed log, or "inline">
issues: <list of problems encountered, or "none">
recommendation: <suggested next step, or "none">
END_HERMES_REPORT
```

**status:**
- `PASS` — Objective fully achieved, validation clean.
- `PARTIAL` — Objective partially achieved, issues remain.
- `FAIL` — Objective not achieved, errors encountered.
- `BLOCKED` — Could not proceed due to external issue.

---

## Judging Rules

1. **Never execute** — OpenClaw only plans and judges. No shell commands, no file writes, no git operations.
2. **Never fabricate** — Do not invent commit hashes, test results, or report paths. Use only what Hermes provides.
3. **No report, no judge** — If Hermes report is missing (inline or file), OpenClaw can only generate `plan` (first command). Cannot pretend to `judge`.
4. **Incomplete report** — If report is missing required fields (status, summary, changed_files), decision must be `REPAIR_COMMAND` asking Hermes to complete the report, or `NEEDS_HUMAN_REVIEW`.
5. **judge-path strictness** — File-based reports must pass all 15 checks (see judge-path section). Any violation → `REPAIR_COMMAND` or `BLOCKED`. No semantic leniency for missing keys or merged fields.
6. **Default mindset** — Personal project: concise steps, minimal ceremony. No complex backup/staging/rollback unless user explicitly requests.
7. **Human checkpoint** — Any `implement` or `commit` command_type should default to `requires_human_approval: true` unless user explicitly overrides.

---

## Workflow

```
User Goal
    → [plan] → OpenClaw generates DECISION + COMMAND_1
        → Hermes executes COMMAND_1 → generates REPORT_1
    → [judge] → OpenClaw reads REPORT_1 from Telegram text
    → [judge-path] → OpenClaw reads REPORT_1 from file at report_path
        → If DONE → stop, human review points
        → If NEXT_COMMAND → generate COMMAND_2
        → If REPAIR_COMMAND → generate fixed COMMAND_1_retry
        → If NEEDS_HUMAN_REVIEW / BLOCKED → stop, explain
```

**judge-path vs judge:**
- `judge` (inline): Hermes pastes `BEGIN_HERMES_REPORT` block into Telegram. Risk of transport reformatting. Acceptable for quick, informal rounds.
- `judge-path` (file): Hermes writes `BEGIN_HERMES_REPORT` to a file, then sends only `HERMES_STATUS` + `HERMES_REPORT_PATH` in Telegram. OpenClaw reads the file directly. Guarantees exact byte-level fidelity. **Recommended for strict compliance.**

---

## Example: plan Mode

**Input:** "Add user authentication to my Express app"

**Output:**
```
BEGIN_OPENCLAW_DECISION
goal_id: auth-express-20260614
iteration: 1
decision: NEXT_COMMAND
requires_human_approval: true
reason: First step: inspect current codebase to determine where auth fits
next_expected_result: List of relevant files and current auth state (none/partial)
END_OPENCLAW_DECISION

BEGIN_HERMES_COMMAND
goal_id: auth-express-20260614
iteration: 1
command_type: inspect
objective: Map current project structure and identify auth-related files
context: Express app, unknown auth status
working_directory: .
instructions:
  1. List project root files and directory structure
  2. Check package.json for existing auth dependencies
  3. Search for existing auth middleware or user models
  4. Check for existing session/JWT configuration
validation: Provide a clear summary of current auth state
report_back: File tree, relevant files list, current auth status, recommended approach
stop_conditions: If no package.json or not an Express app, report BLOCKED
END_HERMES_COMMAND
```

---

## Example: judge Mode (after Hermes report)

**Input:** DECISION_1 + COMMAND_1 + Hermes REPORT_1 (status: PASS, found no auth)

**Output:**
```
BEGIN_OPENCLAW_DECISION
goal_id: auth-express-20260614
iteration: 2
decision: NEXT_COMMAND
requires_human_approval: true
reason: Inspection complete. No auth exists. Proceed with implementing passport-local strategy.
next_expected_result: Working login route with user model and session support
END_OPENCLAW_DECISION

BEGIN_HERMES_COMMAND
goal_id: auth-express-20260614
iteration: 2
command_type: implement
objective: Implement basic passport-local authentication
context: Express app, no existing auth. Add minimal working login.
working_directory: .
instructions:
  1. Install passport, passport-local, express-session
  2. Create models/User.js with minimal fields (username, password hash)
  3. Create middleware/auth.js with passport-local strategy
  4. Add login/logout routes in routes/auth.js
  5. Wire up in app.js with session middleware
validation: Login route accepts POST /login with username/password and creates session
report_back: Changed files, installed packages, test curl command and result
stop_conditions: If npm install fails, report BLOCKED with error output
END_HERMES_COMMAND
```

---

## Example: judge Mode (REPAIR_COMMAND)

**Input:** Hermes REPORT with status: FAIL, issues: "npm install failed, lockfile conflict"

**Output:**
```
BEGIN_OPENCLAW_DECISION
goal_id: auth-express-20260614
iteration: 2
decision: REPAIR_COMMAND
requires_human_approval: false
reason: Hermes failed at dependency install due to lockfile conflict. Repair: remove lockfile and reinstall.
next_expected_result: Clean npm install with new packages added
END_OPENCLAW_DECISION

BEGIN_HERMES_COMMAND
goal_id: auth-express-20260614
iteration: 2.1
command_type: repair
objective: Resolve lockfile conflict and install dependencies cleanly
context: Previous npm install failed with lockfile conflict
working_directory: .
instructions:
  1. Delete package-lock.json and node_modules/
  2. Run npm install (will regenerate clean lockfile)
  3. Run npm install passport passport-local express-session
validation: npm install completes without errors, node_modules/ populated
report_back: npm install output, final package.json dependencies list
stop_conditions: If npm install still fails after lockfile removal, report BLOCKED
END_HERMES_COMMAND
```

---

## Example: judge-path Mode (file-based report reading)

**Input:** Hermes lightweight status:
```
HERMES_STATUS: REPORT_WRITTEN
HERMES_REPORT_PATH: ~/.hermes/workspace/reports/hermes-report-001.md
```

**OpenClaw reads file at `~/.hermes/workspace/reports/hermes-report-001.md`:**
```
BEGIN_HERMES_REPORT
goal_id: auth-express-20260614
iteration: 1
status: PASS
summary: No existing auth found. Express app with standard structure.
changed_files: none
commands_run: ls -la, cat package.json, grep -r "auth\|passport\|jwt" --include="*.js" .
validation_result: Confirmed: no auth middleware, no user models, no session config
commit: none
report_path: ~/.hermes/workspace/reports/hermes-report-001.md
issues: none
recommendation: Implement passport-local strategy with express-session
END_HERMES_REPORT
```

**Output:**
```
BEGIN_OPENCLAW_DECISION
goal_id: auth-express-20260614
iteration: 2
decision: NEXT_COMMAND
requires_human_approval: true
reason: Inspection complete. No auth exists. Proceed with implementing passport-local strategy.
next_expected_result: Working login route with user model and session support
END_OPENCLAW_DECISION

BEGIN_HERMES_COMMAND
goal_id: auth-express-20260614
iteration: 2
command_type: implement
objective: Implement basic passport-local authentication
...
END_HERMES_COMMAND
```

---

## Example: judge-path Mode (file missing)

**Input:** Hermes lightweight status:
```
HERMES_STATUS: REPORT_WRITTEN
HERMES_REPORT_PATH: ~/.hermes/workspace/reports/missing-report.md
```

**OpenClaw attempts to read file — file does not exist.**

**Output:**
```
BEGIN_OPENCLAW_DECISION
goal_id: auth-express-20260614
iteration: 1
decision: BLOCKED
requires_human_approval: true
reason: Hermes reported a report was written but file at ~/.hermes/workspace/reports/missing-report.md does not exist. File-based report protocol requires the file to be present.
next_expected_result: Hermes re-runs and writes report to a valid path, or switches to inline judge mode
END_OPENCLAW_DECISION

---
HUMAN REVIEW POINTS
- Accomplished: No progress possible without report file
- Uncertain: Whether Hermes failed to write or path is wrong
- Recommended: Ask Hermes to confirm file path and re-execute, or fallback to inline judge
- Verify files: None
---
```

---

## Example: judge-path Mode (report malformed)

**Input:** File exists but content is:
```
BEGIN_HERMES_REPORT
openclaw-command-executor-format-hardening-20260614
iteration: 1
status: PASS
...
END_HERMES_REPORT
```

**Output:**
```
BEGIN_OPENCLAW_DECISION
goal_id: openclaw-command-executor-format-hardening-20260614
iteration: 1
decision: REPAIR_COMMAND
requires_human_approval: false
reason: Report file exists but field violations: (1) goal_id key missing (second line shows raw value without `goal_id:` prefix); (2) commands_run field missing. 2 of 13 strict checks failed.
next_expected_result: Hermes re-writes report with strict key:value format for all fields
END_OPENCLAW_DECISION
```

---

## Example: auto-spec Mode

**Input:** "auto-spec for Node.js projects"

**Output:** (Protocol document covering all fields above + recommended relay automation rules for a future script. No actual DECISION or COMMAND generated.)

---

## Human Review Points

When decision is DONE, NEEDS_HUMAN_REVIEW, or BLOCKED, OpenClaw must include:

1. **What was accomplished** (iterations completed, commands executed)
2. **What remains uncertain** (if any)
3. **Recommended next action** (even if BLOCKED)
4. **Files to verify** (changed_files from all reports)

Format:
```
---
HUMAN REVIEW POINTS
- Accomplished: ...
- Uncertain: ...
- Recommended: ...
- Verify files: ...
---
```

---

## Safety & Boundaries

- OpenClaw never executes shell commands (no `exec`, no `write` to project files).
- OpenClaw never modifies the target project's code, configs, or docs.
- OpenClaw never creates fake commits, test results, or report paths.
- If Hermes report is missing: OpenClaw outputs `NEEDS_HUMAN_REVIEW` with reason "Missing Hermes report".
- If Hermes report is incomplete: OpenClaw outputs `REPAIR_COMMAND` to request complete report, or `NEEDS_HUMAN_REVIEW` if ambiguous.
- Default: personal project mindset. No elaborate staging, backup, or rollback unless explicitly requested.
- All `implement`/`commit` type commands default to `requires_human_approval: true`.

---

## Version

1.1.0 — 2026-06-14

Changelog:
- v1.2.0: Hardened plan mode to emit exactly one main command block. Clarified 11-field schema vs 15-point format validation. Fixed judge prompt to use separate-line format (`/skill hermes-agent-loop judge-path` + `report_path:`). Added anti-drift examples for old notification format, multi-command emission, and scope expansion.
- v1.1.0: Added `judge-path` mode for file-based report reading (bypasses Telegram transport reformatting). Added Hermes lightweight notification format (`HERMES_STATUS` + `HERMES_REPORT_PATH`). Added 15-point strict validation checklist for judge-path.
- v1.0.0: Initial skill with `plan`, `judge`, `auto-spec` modes.
