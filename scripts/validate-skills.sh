#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
ERRORS=0

echo "=== Validating agent-loop skills ==="

# 1. Check SKILL.md files exist
echo ""
echo "1. Checking SKILL.md files..."
for f in \
    "$REPO_DIR/skills/openclaw/hermes-agent-loop/SKILL.md" \
    "$REPO_DIR/skills/hermes/openclaw-command-executor/SKILL.md"; do
    if [ -f "$f" ]; then
        echo "  ✓ $f"
    else
        echo "  ✗ MISSING: $f"
        ERRORS=$((ERRORS + 1))
    fi
done

# 2. Check NO old format "REPORT_WRITTEN /path" (without HERMES_STATUS:)
echo ""
echo "2. Checking for old notification format..."
# Look for standalone "REPORT_WRITTEN" lines that are NOT part of "HERMES_STATUS: REPORT_WRITTEN"
OLD_FORMAT=$(grep -r "REPORT_WRITTEN" "$REPO_DIR" --exclude-dir=.git --exclude-dir=examples --exclude="*.sh" | grep -v "HERMES_STATUS: REPORT_WRITTEN" | grep -v "HERMES_REPORT_WRITTEN" | grep -v "judge-path" | grep -v "15-point" || true)
if [ -n "$OLD_FORMAT" ]; then
    echo "  ✗ Old format found:"
    echo "$OLD_FORMAT" | head -5
    ERRORS=$((ERRORS + 1))
else
    echo "  ✓ No old standalone REPORT_WRITTEN format found"
fi

# 3. Check HERMES_STATUS: REPORT_WRITTEN exists in skills
echo ""
echo "3. Checking for HERMES_STATUS: REPORT_WRITTEN in skills..."
if grep -r "HERMES_STATUS: REPORT_WRITTEN" "$REPO_DIR/skills/" >/dev/null 2>&1; then
    echo "  ✓ HERMES_STATUS: REPORT_WRITTEN found in skills"
else
    echo "  ✗ HERMES_STATUS: REPORT_WRITTEN NOT found in skills"
    ERRORS=$((ERRORS + 1))
fi

# 4. Check HERMES_REPORT_PATH exists in skills
echo ""
echo "4. Checking for HERMES_REPORT_PATH in skills..."
if grep -r "HERMES_REPORT_PATH" "$REPO_DIR/skills/" >/dev/null 2>&1; then
    echo "  ✓ HERMES_REPORT_PATH found in skills"
else
    echo "  ✗ HERMES_REPORT_PATH NOT found in skills"
    ERRORS=$((ERRORS + 1))
fi

# 5. Check OpenClaw skill contains required keywords
echo ""
echo "5. Checking OpenClaw skill content..."
OPENCLAW_SKILL="$REPO_DIR/skills/openclaw/hermes-agent-loop/SKILL.md"
for keyword in "plan" "judge-path" "BEGIN_OPENCLAW_DECISION" "BEGIN_HERMES_COMMAND" "exactly one main"; do
    if grep -q "$keyword" "$OPENCLAW_SKILL"; then
        echo "  ✓ '$keyword' found"
    else
        echo "  ✗ '$keyword' NOT found"
        ERRORS=$((ERRORS + 1))
    fi
done

# 6. Check Hermes skill contains required keywords
echo ""
echo "6. Checking Hermes skill content..."
HERMES_SKILL="$REPO_DIR/skills/hermes/openclaw-command-executor/SKILL.md"
for keyword in "BEGIN_HERMES_REPORT" "canonical report" "detail artifact" "do not expand scope" "stop after requested command passes"; do
    if grep -q "$keyword" "$HERMES_SKILL"; then
        echo "  ✓ '$keyword' found"
    else
        echo "  ✗ '$keyword' NOT found"
        ERRORS=$((ERRORS + 1))
    fi
done

# 7. Check README has skill install instructions
echo ""
echo "7. Checking README for skill install instructions..."
if grep -q "install-skills.sh" "$REPO_DIR/README.md" && grep -q "install-all.sh" "$REPO_DIR/README.md"; then
    echo "  ✓ Skill install instructions found in README.md"
else
    echo "  ✗ Skill install instructions NOT found in README.md"
    ERRORS=$((ERRORS + 1))
fi

# 8. Check README.zh-CN.md has skill install instructions
echo ""
echo "8. Checking README.zh-CN.md for skill install instructions..."
if grep -q "install-skills.sh" "$REPO_DIR/README.zh-CN.md" && grep -q "install-all.sh" "$REPO_DIR/README.zh-CN.md"; then
    echo "  ✓ Skill install instructions found in README.zh-CN.md"
else
    echo "  ✗ Skill install instructions NOT found in README.zh-CN.md"
    ERRORS=$((ERRORS + 1))
fi

# 9. Check judge prompt format
echo ""
echo "9. Checking judge prompt format..."
if grep -q "/skill hermes-agent-loop judge-path" "$OPENCLAW_SKILL"; then
    echo "  ✓ Correct judge prompt format found"
else
    echo "  ✗ Correct judge prompt format NOT found"
    ERRORS=$((ERRORS + 1))
fi

# 10. Check 11-field vs 15-point clarification
echo ""
echo "10. Checking 11-field vs 15-point clarification..."
if grep -q "11-field schema" "$HERMES_SKILL" && grep -q "15-point" "$HERMES_SKILL"; then
    echo "  ✓ 11-field vs 15-point clarification found"
else
    echo "  ✗ 11-field vs 15-point clarification NOT found"
    ERRORS=$((ERRORS + 1))
fi

# Summary
echo ""
if [ $ERRORS -eq 0 ]; then
    echo "=== Validation PASSED ==="
    exit 0
else
    echo "=== Validation FAILED: $ERRORS error(s) ==="
    exit 1
fi
