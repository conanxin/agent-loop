#!/usr/bin/env bash
set -euo pipefail

REPO_URL="https://github.com/conanxin/agent-loop.git"
AGENT_LOOP_HOME="${AGENT_LOOP_HOME:-$HOME/.agent-loop}"
BIN_DIR="$AGENT_LOOP_HOME/bin"

echo "Installing agent-loop..."

# Clone or update repository
if [ -d "$AGENT_LOOP_HOME/.git" ]; then
    echo "Directory $AGENT_LOOP_HOME exists. Updating..."
    cd "$AGENT_LOOP_HOME"
    git pull origin main
else
    echo "Cloning repository..."
    git clone "$REPO_URL" "$AGENT_LOOP_HOME"
fi

# Add to PATH if not already present
if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
    echo "export PATH=\"$BIN_DIR:\$PATH\"" >> "$HOME/.bashrc"
    echo "Added $BIN_DIR to PATH. Please run: source ~/.bashrc"
fi

# Verify installation
echo "Verifying installation..."
export PATH="$BIN_DIR:$PATH"

for tool in agent-loop-init-goal agent-loop-set-state agent-loop-show agent-loop-relay; do
    if command -v "$tool" &> /dev/null; then
        echo "✓ $tool found"
    else
        echo "✗ $tool not found"
        exit 1
    fi
done

# Create goals directory if not exists
mkdir -p "$AGENT_LOOP_HOME/goals"

echo ""
echo "Installation complete!"
echo "Run 'source ~/.bashrc' to update PATH, then:"
echo "  agent-loop-init-goal my-goal \"My first goal\""
