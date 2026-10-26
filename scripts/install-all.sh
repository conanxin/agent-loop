#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "=== agent-loop Full Install ==="
"$SCRIPT_DIR/install.sh"
"$SCRIPT_DIR/install-skills.sh"
"$SCRIPT_DIR/smoke-test.sh"
echo "=== Installation Complete ==="
