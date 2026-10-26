#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
OPENCLAW_SKILLS_DIR="${OPENCLAW_SKILLS_DIR:-$HOME/.openclaw/workspace/skills}"
HERMES_SKILLS_DIR="${HERMES_SKILLS_DIR:-$HOME/.hermes/skills}"

echo "Installing agent-loop skills from $REPO_ROOT"
OPENCLAW_DEST="$OPENCLAW_SKILLS_DIR/hermes-agent-loop"
HERMES_DEST="$HERMES_SKILLS_DIR/openclaw-command-executor"
mkdir -p "$OPENCLAW_DEST" "$HERMES_DEST"
cp "$REPO_ROOT/skills/openclaw/hermes-agent-loop/SKILL.md" "$OPENCLAW_DEST/"
cp "$REPO_ROOT/skills/hermes/openclaw-command-executor/SKILL.md" "$HERMES_DEST/"
echo "Installed OpenClaw and Hermes skills; reload the agents if needed."
