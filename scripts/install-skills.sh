#!/usr/bin/env bash
set -euo pipefail

AGENT_LOOP_HOME="${AGENT_LOOP_HOME:-$HOME/.agent-loop}"
OPENCLAW_SKILLS_DIR="${OPENCLAW_SKILLS_DIR:-$HOME/.openclaw/workspace/skills}"
HERMES_SKILLS_DIR="${HERMES_SKILLS_DIR:-$HOME/.hermes/skills}"

echo "Installing agent-loop skills..."

# OpenClaw skill
OPENCLAW_DEST="$OPENCLAW_SKILLS_DIR/hermes-agent-loop"
mkdir -p "$OPENCLAW_DEST"
cp "$AGENT_LOOP_HOME/skills/openclaw/hermes-agent-loop/SKILL.md" "$OPENCLAW_DEST/"
echo "✓ OpenClaw skill installed: $OPENCLAW_DEST/SKILL.md"

# Hermes skill
HERMES_DEST="$HERMES_SKILLS_DIR/openclaw-command-executor"
mkdir -p "$HERMES_DEST"
cp "$AGENT_LOOP_HOME/skills/hermes/openclaw-command-executor/SKILL.md" "$HERMES_DEST/"
echo "✓ Hermes skill installed: $HERMES_DEST/SKILL.md"

echo ""
echo "Skills installation complete!"
echo ""
echo "To verify OpenClaw skill:"
echo "  cat $OPENCLAW_DEST/SKILL.md"
echo ""
echo "To verify Hermes skill:"
echo "  cat $HERMES_DEST/SKILL.md"
echo ""
echo "Note: You may need to reload your agent for skills to be recognized."
