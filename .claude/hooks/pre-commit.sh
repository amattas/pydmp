#!/usr/bin/env bash
# Claude Code pre-commit hook — mirrors the aviato-managed CI verify (ruff owns
# formatting, linting, and the bandit-family security rules via ruff.toml).

# Parse tool input to check if this is a git commit command
COMMAND=$(echo "$CLAUDE_TOOL_INPUT" | python3 -c "import sys, json; print(json.load(sys.stdin).get('command', ''))" 2>/dev/null)

# Only run checks for git commit commands
if ! echo "$COMMAND" | grep -qE 'git\s+commit'; then
    exit 0
fi

echo "Running pre-commit checks..."
FAILED=0

if command -v ruff &>/dev/null; then
    if ! OUTPUT=$(ruff format --check src tests 2>&1); then
        echo "FAILED: ruff format"
        echo "$OUTPUT"
        FAILED=1
    fi
    if ! OUTPUT=$(ruff check src tests 2>&1); then
        echo "FAILED: ruff"
        echo "$OUTPUT"
        FAILED=1
    fi
else
    echo "SKIP: ruff not found"
fi

# end-of-file-fixer (ensure files end with newline)
while IFS= read -r -d '' f; do
    if [ -s "$f" ] && [ "$(tail -c 1 "$f" | wc -l)" -eq 0 ]; then
        echo "FAILED: missing newline at end of $f"
        FAILED=1
    fi
done < <(find src tests -name '*.py' -print0 2>/dev/null)

if [ $FAILED -ne 0 ]; then
    echo ""
    echo "Pre-commit checks FAILED. Fix issues before committing."
    exit 2
fi

echo "All pre-commit checks passed."
exit 0
