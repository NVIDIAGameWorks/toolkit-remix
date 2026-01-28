#!/bin/bash
# Uninstall pre-commit hooks

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${SCRIPT_DIR}/.venv"

echo "Uninstalling pre-commit hooks..."
echo ""

if [ -f "${VENV_DIR}/bin/pre-commit" ]; then
    "${VENV_DIR}/bin/pre-commit" uninstall
    "${VENV_DIR}/bin/pre-commit" uninstall --hook-type pre-push
else
    echo "pre-commit not found in .venv, skipping..."
fi

echo ""
echo "Hooks uninstalled."
echo ""
echo "To remove the virtual environment, delete the .venv folder."
