#!/bin/bash
# Uninstall pre-commit hooks
# Usage: uninstall_hooks.sh [-c]
#   -c  Clean up the .venv directory after uninstalling hooks

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${SCRIPT_DIR}/.venv"
CLEAN_VENV=""

# Parse arguments
if [ "$1" = "-c" ]; then
    CLEAN_VENV="1"
fi

echo "Uninstalling pre-commit hooks..."
echo ""

if [ -f "${VENV_DIR}/bin/pre-commit" ]; then
    "${VENV_DIR}/bin/pre-commit" uninstall
    "${VENV_DIR}/bin/pre-commit" uninstall --hook-type pre-push
else
    echo "pre-commit not found in .venv, skipping..."
fi

if [ -n "$CLEAN_VENV" ]; then
    echo ""
    echo "Cleaning up .venv directory..."
    rm -rf "${VENV_DIR}"
    if [ -d "${VENV_DIR}" ]; then
        echo "WARNING: Could not fully remove .venv directory"
    else
        echo ".venv directory removed."
    fi
fi

echo ""
echo "Hooks uninstalled."
echo ""
if [ -z "$CLEAN_VENV" ]; then
    echo "To also remove the virtual environment, run: ./uninstall_hooks.sh -c"
    echo "Or delete the .venv directory manually."
    echo ""
fi
echo "TIP: If you are uninstalling because you had issues, you can try reinstalling with:"
echo ""
echo "  ./install_hooks.sh -f"
echo ""
echo "This replaces existing hooks and often resolves conflicts with legacy hooks."
