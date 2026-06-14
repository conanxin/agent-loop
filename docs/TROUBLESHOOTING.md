---
title: Troubleshooting Guide
version: 1.0
---

# TROUBLESHOOTING.md

## Common Issues

### State Mismatch

**Symptom**: `relay --decision-path` fails with "Decision ingestion is only valid after judge prompt / report written."

**Cause**: Current state is not `OPENCLAW_JUDGING` or `HERMES_REPORT_WRITTEN`.

**Fix**:
```bash
# Check current state
agent-loop-show <goal-id>

# If state is wrong, manually correct
agent-loop-set-state <goal-id> OPENCLAW_JUDGING
```

### Missing Required Fields

**Symptom**: `Error: decision file missing required fields: next_expected_result`

**Cause**: Decision file is missing one or more required fields.

**Fix**: Add all 6 required fields:
```yaml
BEGIN_OPENCLAW_DECISION
goal_id: <goal-id>
iteration: 1
decision: DONE
requires_human_approval: false
reason: <explanation>
next_expected_result: <expected result>
END_OPENCLAW_DECISION
```

### File Not Found

**Symptom**: `Error: decision file not found: <path>`

**Cause**: File path is incorrect or file doesn't exist.

**Fix**:
```bash
# Verify file exists
ls -la <path>

# Use absolute path, not relative
agent-loop-relay --decision-path <goal-id> /absolute/path/to/decision.md
```

### Telegram Transport Corruption

**Symptom**: Report content is truncated or garbled in Telegram.

**Cause**: Telegram has message size limits and Markdown rendering issues.

**Fix**: Use the file-based relay. Telegram should only carry:
```
HERMES_STATUS: REPORT_WRITTEN
HERMES_REPORT_PATH: <absolute-path>
```

All structured data goes in `hermes-reports/<iteration>.md`.

### Goal Already Exists

**Symptom**: `Goal already exists: <goal-id>`

**Cause**: Goal directory already exists.

**Fix**:
```bash
# Check if goal is empty or has content
ls -la ~/.agent-loop/goals/<goal-id>/

# If empty, reuse it
# If has content, use a new goal-id
agent-loop-init-goal <goal-id>-r2 "Description"
```

### Report Path Mismatch

**Symptom**: `report_path` in report doesn't match actual file location.

**Cause**: Report was moved after creation or path was wrong.

**Fix**: Always use absolute paths in `report_path`:
```yaml
report_path: ~/.agent-loop/goals/<goal-id>/hermes-reports/001.md
```

### Git Status Not Empty After Validation

**Symptom**: `git status --short` shows modified files after `make validate`.

**Cause**: Some tools write files even during "validation".

**Fix**:
```bash
# Check which files were modified
git status --short

# Revert changes
git checkout -- .

# Use read-only alternatives
make validate  # instead of make test
```

### Decision Value Invalid

**Symptom**: `Invalid decision value: <value>`

**Cause**: Decision is not one of the 6 allowed values.

**Fix**: Use one of:
- `DONE`
- `NEXT_COMMAND`
- `REPAIR_COMMAND`
- `PARTIAL`
- `BLOCKED`
- `NEEDS_HUMAN_REVIEW`

### Goal ID Mismatch

**Symptom**: `Decision goal_id mismatch: <decision.goal_id> != <goal_id>`

**Cause**: Decision file's `goal_id` doesn't match the goal directory.

**Fix**: Ensure `goal_id` in decision file matches the directory name.

### Relay Not in PATH

**Symptom**: `agent-loop-relay: command not found`

**Cause**: `~/.agent-loop/bin` is not in PATH.

**Fix**:
```bash
export PATH="$HOME/.agent-loop/bin:$PATH"
# Add to ~/.bashrc for persistence
echo 'export PATH="$HOME/.agent-loop/bin:$PATH"' >> ~/.bashrc
```

## Debug Mode

Enable verbose output:
```bash
# Add to scripts or run manually
set -x
agent-loop-relay --once <goal-id>
set +x
```

## Getting Help

1. Check [SPEC.md](SPEC.md) for protocol details
2. Check [MANUAL_RELAY_WORKFLOW.md](MANUAL_RELAY_WORKFLOW.md) for step-by-step guide
3. Check [SAFETY_BOUNDARIES.md](SAFETY_BOUNDARIES.md) for safety rules
4. Open an issue at https://github.com/conanxin/agent-loop/issues

## Error Code Reference

| Exit Code | Meaning | Action |
|---|---|---|
| 0 | Success | Continue workflow |
| 1 | General error | Check error message, fix issue |
| 2 | Missing required fields | Add missing fields to protocol block |
| 3 | File not found | Verify file path exists |
| 4 | State mismatch | Check and correct state |
| 5 | Decision invalid | Use valid decision value |
