---
title: Safety Boundaries
version: 1.0
---

# SAFETY_BOUNDARIES.md

## Red Lines

### 1. No Auto-Execution

**Rule**: The relay prints commands; it never executes them automatically.

**Why**: Prevents accidental destructive operations.

**Implementation**:
- `relay --once` prints the command but keeps state at `COMMAND_READY`
- Human must explicitly run `--mark-dispatched` to advance

### 2. No Real Project Modification Without Approval

**Rule**: Validation tasks must use read-only commands only.

**Safe commands**:
- `make validate` (read-only)
- `git status` (read-only)
- `git log` (read-only)
- `ls`, `cat`, `grep` (read-only)

**Unsafe commands** (require explicit approval):
- `make test` (may write files)
- `make build` (writes generated files)
- `git commit` (modifies repository)
- `rm` (destructive)
- Any file write operation

### 3. No Token Leakage

**Rule**: No secrets, tokens, or credentials in any protocol file.

**Forbidden in protocol files**:
- API keys
- GitHub tokens (`gho_`)
- Telegram bot tokens
- Passwords
- Personal paths (`/home/username`)

**Safe alternatives**:
- Use `~/.agent-loop` instead of absolute home paths
- Store tokens in `.env` (gitignored)
- Reference environment variables: `${TOKEN}` instead of literal values

### 4. No Path Leakage

**Rule**: Use generic paths in all documentation and examples.

**Before**:
```
~/.agent-loop/goals/my-project
```

**After**:
```
~/.agent-loop/goals/my-project
```

### 5. State Machine Enforcement

**Rule**: `--decision-path` only valid in specific states.

**Valid states for `--decision-path`**:
- `OPENCLAW_JUDGING`
- `HERMES_REPORT_WRITTEN`

**Error message**:
```
Decision ingestion is only valid after judge prompt / report written.
```

### 6. Git Status Verification

**Rule**: After any validation task, verify `git status --short` is empty.

**Implementation**:
```bash
if [ -z "$(git status --short)" ]; then
    echo "PASS: No files modified"
else
    echo "FAIL: Files were modified"
    git status --short
    exit 1
fi
```

### 7. No Daemon or Service Creation

**Rule**: agent-loop does not create background services.

**Why**: Keeps the system simple and stateless.

### 8. No External API Calls

**Rule**: agent-loop tools do not call external APIs.

**Exceptions**:
- Hermes may call APIs as part of command execution
- OpenClaw may call APIs as part of its operation
- But the relay itself is file-system only

## Safety Checklist

Before running any command:

- [ ] Is this a read-only operation?
- [ ] Will this modify any real project files?
- [ ] Are there any secrets in the command?
- [ ] Is the state machine in the correct state?
- [ ] Have I verified the previous step completed successfully?

## Incident Response

If a safety boundary is violated:

1. **Stop immediately**: Do not continue the workflow
2. **Assess damage**: Check `git status`, file modifications
3. **Revert if needed**: `git checkout -- .` or restore from backup
4. **Document**: Add to issues/ directory with timestamp
5. **Fix root cause**: Update scripts or documentation to prevent recurrence

## Examples

### Good: Read-only validation

```bash
cd ~/projects/my-project
make validate
git status --short  # Should be empty
```

### Bad: Destructive without check

```bash
cd ~/projects/my-project
make test  # Writes site/index.embedded.html
make build  # Writes generated/index.json
```

### Good: Using environment variables

```bash
# .env (gitignored)
TELEGRAM_BOT_TOKEN=your_token_here

# In scripts
source .env
curl -H "Authorization: Bearer $TELEGRAM_BOT_TOKEN" ...
```

### Bad: Hardcoded token

```bash
# NEVER do this
curl -H "Authorization: Bearer gho_xxxxxxxxxxxx" ...
```
