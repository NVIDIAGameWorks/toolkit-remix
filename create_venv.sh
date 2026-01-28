#!/bin/bash
# Create a Python virtual environment using packman's Python

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${SCRIPT_DIR}/.venv"

if [ -f "${VENV_DIR}/bin/python" ]; then
    echo "Virtual environment already exists at ${VENV_DIR}"
    exit 0
fi

echo "Creating virtual environment..."
"${SCRIPT_DIR}/tools/packman/python.sh" -m venv "${VENV_DIR}"

echo ""
echo "Virtual environment created at ${VENV_DIR}"
echo "Activate with: source .venv/bin/activate"
