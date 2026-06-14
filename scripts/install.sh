#!/bin/bash
# install.sh — Install agent-loop

set -e

REPO_URL="https://github.com/conanxin/agent-loop.git"
INSTALL_DIR="$HOME/.agent-loop"
BIN_DIR="$INSTALL_DIR/bin"

echo "Installing agent-loop..."

# Clone or update repository
if [ -d "$INSTALL_DIR" ]; then
    echo "Directory $INSTALL_DIR exists. Updating..."
    cd "$INSTALL_DIR"
    git pull origin main
else
    echo "Cloning repository..."
    git clone "$REPO_URL" "$INSTALL_DIR"
fi

# Add to PATH if not already present
if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
    echo "export PATH=\"$BIN_DIR:\$PATH\"" >> "$HOME/.bashrc"
    echo "Added $BIN_DIR to PATH. Please run: source ~/.bashrc"
fi

# Verify installation
echo "Verifying installation..."
export PATH="$BIN_DIR:$PATH"

if command -v agent-loop-init-goal &> /dev/null; then
    echo "✓ agent-loop-init-goal found"
else
    echo "✗ agent-loop-init-goal not found"
    exit 1
fi

if command -v agent-loop-relay &> /dev/null; then
    echo "✓ agent-loop-relay found"
else
    echo "✗ agent-loop-relay not found"
    exit 1
fi

# Create goals directory if not exists
mkdir -p "$INSTALL_DIR/goals"

echo ""
echo "Installation complete!"
echo "Run 'source ~/.bashrc' to update PATH, then:"
echo "  agent-loop-init-goal my-goal \"My first goal\""
