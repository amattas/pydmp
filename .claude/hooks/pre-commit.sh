#!/usr/bin/env bash
# Claude Code pre-commit hook
# Replaces .pre-commit-config.yaml checks: black, ruff, end-of-file-fixer, trailing-whitespace, bandit

# Parse tool input to check if this is a git commit command
COMMAND=$(echo "$CLAUDE_TOOL_INPUT" | python3 -c "import sys, json; print(json.load(sys.stdin).get('command', ''))" 2>/dev/null)

# Only run checks for git commit commands
if ! echo "$COMMAND" | grep -qE 'git\s+commit'; then
    exit 0
fi

echo "Running pre-commit checks..."
FAILED=0

# black (code formatter) - check only
if command -v black &>/dev/null; then
    OUTPUT=$(black --check src tests 2>&1)
    if [ $? -ne 0 ]; then
        echo "FAILED: black"
        echo "$OUTPUT"
        FAILED=1
    fi
else
    echo "SKIP: black not found"
fi

# ruff (linter)
if command -v ruff &>/dev/null; then
    OUTPUT=$(ruff check src tests 2>&1)
    if [ $? -ne 0 ]; then
        echo "FAILED: ruff"
        echo "$OUTPUT"
        FAILED=1
    fi
else
    echo "SKIP: ruff not found"
fi

# trailing whitespace
TRAILING=$(grep -rn ' $' src/ tests/ --include='*.py' 2>/dev/null)
if [ -n "$TRAILING" ]; then
    echo "FAILED: trailing whitespace"
    echo "$TRAILING"
    FAILED=1
fi

# end-of-file-fixer (ensure files end with newline)
for f in $(find src tests -name '*.py' 2>/dev/null); do
    if [ -s "$f" ] && [ "$(tail -c 1 "$f" | wc -l)" -eq 0 ]; then
        echo "FAILED: missing newline at end of $f"
        FAILED=1
    fi
done

# bandit (security)
if command -v bandit &>/dev/null; then
    OUTPUT=$(bandit -r src -x tests -q 2>&1)
    if [ $? -ne 0 ]; then
        echo "FAILED: bandit"
        echo "$OUTPUT"
        FAILED=1
    fi
else
    echo "SKIP: bandit not found"
fi

if [ $FAILED -ne 0 ]; then
    echo ""
    echo "Pre-commit checks FAILED. Fix issues before committing."
    exit 2
fi

echo "All pre-commit checks passed."
exit 0
