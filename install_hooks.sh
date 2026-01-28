#!/bin/bash
# Install pre-commit hooks for formatting (on commit) and linting (on push)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${SCRIPT_DIR}/.venv"

echo "Installing pre-commit hooks..."
echo ""

# Create venv if it doesn't exist
"${SCRIPT_DIR}/create_venv.sh"

# Install pre-commit into the venv
"${VENV_DIR}/bin/pip" install pre-commit==4.0.1

# Install the hooks
"${VENV_DIR}/bin/pre-commit" install
"${VENV_DIR}/bin/pre-commit" install --hook-type pre-push

echo ""
echo "Hooks installed successfully!"
echo "  - Commit: auto-format with ruff"
echo "  - Push: lint check with ruff"
echo ""
echo "Skip with: git commit --no-verify / git push --no-verify"
