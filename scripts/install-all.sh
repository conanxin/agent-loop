#!/usr/bin/env bash
set -euo pipefail

AGENT_LOOP_HOME="${AGENT_LOOP_HOME:-$HOME/.agent-loop}"

echo "=== agent-loop Full Install ==="
echo ""

# Install tools
echo "Step 1: Installing tools..."
"$AGENT_LOOP_HOME/scripts/install.sh"

# Install skills
echo ""
echo "Step 2: Installing skills..."
"$AGENT_LOOP_HOME/scripts/install-skills.sh"

# Run smoke test
echo ""
echo "Step 3: Running smoke test..."
"$AGENT_LOOP_HOME/scripts/smoke-test.sh"

echo ""
echo "=== Installation Complete ==="
echo ""
echo "Next steps:"
echo "  1. Update PATH:"
echo "     export PATH=\"\$HOME/.agent-loop/bin:\$PATH\""
echo ""
echo "  2. Verify a goal:"
echo "     agent-loop-show <goal_id>"
echo ""
echo "  3. Check OpenClaw skill:"
echo "     cat \${OPENCLAW_SKILLS_DIR:-\$HOME/.openclaw/workspace/skills}/hermes-agent-loop/SKILL.md"
echo ""
echo "  4. Check Hermes skill:"
echo "     cat \${HERMES_SKILLS_DIR:-\$HOME/.hermes/skills}/openclaw-command-executor/SKILL.md"
echo ""
echo "  5. Start using:"
echo "     agent-loop-init-goal my-project \"My first goal\""
