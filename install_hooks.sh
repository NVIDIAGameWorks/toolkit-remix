#!/bin/bash
# Install pre-commit hooks for formatting (on commit) and linting (on push)
# Usage: install_hooks.sh [-f]
#   -f  Force install, replacing any existing hooks

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${SCRIPT_DIR}/.venv"
FORCE_FLAG=""

# Parse arguments
if [ "$1" = "-f" ]; then
    FORCE_FLAG="-f"
fi

if [ -n "$FORCE_FLAG" ]; then
    echo "Performing clean install of pre-commit hooks..."
else
    echo "Installing pre-commit hooks..."
fi
echo ""

# Create venv if it doesn't exist
"${SCRIPT_DIR}/create_venv.sh"

# Install pre-commit into the venv
"${VENV_DIR}/bin/pip" install pre-commit==4.0.1

# Install the hooks
"${VENV_DIR}/bin/pre-commit" install $FORCE_FLAG
"${VENV_DIR}/bin/pre-commit" install --hook-type pre-push $FORCE_FLAG

echo ""
echo "Hooks installed successfully!"
echo "  - Commit: auto-format with ruff"
echo "  - Push: lint check with ruff"
echo ""
echo "Skip with: git commit --no-verify / git push --no-verify"

if [ -z "$FORCE_FLAG" ]; then
    echo ""
    echo "TIP: If your hooks fail to run (e.g. pre-push errors), try reinstalling with:"
    echo ""
    echo "  ./install_hooks.sh -f"
    echo ""
    echo "This replaces existing hooks and often resolves conflicts with legacy hooks."
fi
