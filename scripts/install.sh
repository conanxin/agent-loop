#!/usr/bin/env bash
set -euo pipefail

# Install from this checkout, preserving pre-existing ~/.agent-loop/goals.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
AGENT_LOOP_HOME="${AGENT_LOOP_HOME:-$HOME/.agent-loop}"
AGENT_LOOP_HOME="${AGENT_LOOP_HOME/#\~/$HOME}"
BIN_DIR="$AGENT_LOOP_HOME/bin"

echo "Installing agent-loop from $REPO_ROOT"
mkdir -p "$BIN_DIR" "$AGENT_LOOP_HOME/goals"
for source in "$REPO_ROOT"/bin/agent-loop-*; do
    [ -f "$source" ] || continue
    cp "$source" "$BIN_DIR/"
    chmod +x "$BIN_DIR/$(basename "$source")"
done

for tool in agent-loop-init-goal agent-loop-set-state agent-loop-show agent-loop-relay agent-loop-status-json; do
    if [ ! -x "$BIN_DIR/$tool" ]; then
        echo "Missing installed tool: $BIN_DIR/$tool" >&2
        exit 1
    fi
done

echo "Installation complete; existing goal files were not altered."
echo "If needed: export PATH=\"$BIN_DIR:\$PATH\""
