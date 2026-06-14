#!/usr/bin/env bash
set -euo pipefail

# Use AGENT_LOOP_HOME (defaults to ~/.agent-loop) for both
# - Where tools are looked up (PATH)
# - Where goals are stored
AGENT_LOOP_HOME="${AGENT_LOOP_HOME:-$HOME/.agent-loop}"
export PATH="$AGENT_LOOP_HOME/bin:$PATH"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_BIN_DIR="$SCRIPT_DIR/../bin"

# In CI (when AGENT_LOOP_HOME points to a temp dir and bin/ is empty),
# fall back to the repo's bin/ directory.
if [ ! -x "$AGENT_LOOP_HOME/bin/agent-loop-init-goal" ] && [ -d "$REPO_BIN_DIR" ]; then
    export PATH="$REPO_BIN_DIR:$PATH"
fi

GOAL_ID="smoke-test-$(date +%s)"
GOAL_DIR="$AGENT_LOOP_HOME/goals/$GOAL_ID"

echo "=== agent-loop Smoke Test ==="
echo "AGENT_LOOP_HOME: $AGENT_LOOP_HOME"
echo "Goal ID: $GOAL_ID"

# Step 1: Initialize goal
echo ""
echo "Step 1: Initialize goal"
agent-loop-init-goal "$GOAL_ID" "Smoke test goal"

# Step 2: Write dummy command
mkdir -p "$GOAL_DIR/hermes-commands"
cat > "$GOAL_DIR/hermes-commands/001.md" <<'CMDEOF'
BEGIN_HERMES_COMMAND
goal_id: SMOKE_TEST
iteration: 1
command_type: validate
objective: Smoke test validation
context: Synthetic smoke test for agent-loop
working_directory: /tmp
instructions:
  1. Create a temporary file with demo content
  2. Verify the file exists
validation: File exists and contains expected content
report_back: HERMES_STATUS: REPORT_WRITTEN
stop_conditions: If file creation fails, report FAIL
END_HERMES_COMMAND
CMDEOF

# Step 3: Set state to COMMAND_READY
echo ""
echo "Step 3: Set state to COMMAND_READY"
agent-loop-set-state "$GOAL_ID" COMMAND_READY

# Step 4: relay --once (should print, not advance)
echo ""
echo "Step 4: relay --once"
agent-loop-relay --once "$GOAL_ID"

STATE=$(python3 -c "import json; print(json.load(open('$GOAL_DIR/state.json'))['current_state'])")
if [ "$STATE" != "COMMAND_READY" ]; then
    echo "FAIL: State should be COMMAND_READY, got $STATE"
    exit 1
fi
echo "PASS: State is COMMAND_READY"

# Step 5: --mark-dispatched
echo ""
echo "Step 5: --mark-dispatched"
agent-loop-relay --once "$GOAL_ID" --mark-dispatched

STATE=$(python3 -c "import json; print(json.load(open('$GOAL_DIR/state.json'))['current_state'])")
if [ "$STATE" != "DISPATCHED_TO_HERMES" ]; then
    echo "FAIL: State should be DISPATCHED_TO_HERMES, got $STATE"
    exit 1
fi
echo "PASS: State is DISPATCHED_TO_HERMES"

# Step 6: Write report
mkdir -p "$GOAL_DIR/hermes-reports"
cat > "$GOAL_DIR/hermes-reports/001.md" <<'REPEOF'
BEGIN_HERMES_REPORT
goal_id: SMOKE_TEST
iteration: 1
status: PASS
summary: Smoke test report
changed_files: none
commands_run: - smoke test
validation_result: pass
commit: none
report_path: /tmp/smoke-test-report.md
issues: none
recommendation: none
END_HERMES_REPORT
REPEOF

# Step 7: --report-path
echo ""
echo "Step 7: --report-path"
agent-loop-relay --once "$GOAL_ID" --report-path "$GOAL_DIR/hermes-reports/001.md"

STATE=$(python3 -c "import json; print(json.load(open('$GOAL_DIR/state.json'))['current_state'])")
if [ "$STATE" != "HERMES_REPORT_WRITTEN" ]; then
    echo "FAIL: State should be HERMES_REPORT_WRITTEN, got $STATE"
    exit 1
fi
echo "PASS: State is HERMES_REPORT_WRITTEN"

# Step 8: --judge-prompt
echo ""
echo "Step 8: --judge-prompt"
agent-loop-relay --judge-prompt "$GOAL_ID" > /dev/null

# Step 9: --mark-judging
echo ""
echo "Step 9: --mark-judging"
agent-loop-relay --judge-prompt "$GOAL_ID" --mark-judging

STATE=$(python3 -c "import json; print(json.load(open('$GOAL_DIR/state.json'))['current_state'])")
if [ "$STATE" != "OPENCLAW_JUDGING" ]; then
    echo "FAIL: State should be OPENCLAW_JUDGING, got $STATE"
    exit 1
fi
echo "PASS: State is OPENCLAW_JUDGING"

# Step 10: Write decision
mkdir -p "$GOAL_DIR/openclaw-decisions"
cat > "$GOAL_DIR/openclaw-decisions/001.md" <<DECEOF
BEGIN_OPENCLAW_DECISION
goal_id: $GOAL_ID
iteration: 1
decision: DONE
requires_human_approval: false
reason: Smoke test complete
next_expected_result: none
END_OPENCLAW_DECISION
DECEOF

# Step 11: --decision-path
echo ""
echo "Step 11: --decision-path"
agent-loop-relay --decision-path "$GOAL_ID" "$GOAL_DIR/openclaw-decisions/001.md"

STATE=$(python3 -c "import json; print(json.load(open('$GOAL_DIR/state.json'))['current_state'])")
if [ "$STATE" != "DONE" ]; then
    echo "FAIL: State should be DONE, got $STATE"
    exit 1
fi
echo "PASS: State is DONE"

# Step 12: Show final state
echo ""
echo "Step 12: Final state"
agent-loop-show "$GOAL_ID"

# Cleanup
rm -rf "$GOAL_DIR"

echo ""
echo "=== Smoke Test PASSED ==="
