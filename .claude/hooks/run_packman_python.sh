#!/bin/bash
# Cross-platform packman Python wrapper.
# Hooks run in the project root, so relative paths work directly.
# Usage: run_packman_python.sh <script.py> [args...]
SCRIPT="$1"; shift

if [[ "$OS" == "Windows_NT" ]]; then
    cmd //c "tools\\packman\\python.bat" "${SCRIPT//\//\\}" "$@"
else
    tools/packman/python.sh "$SCRIPT" "$@"
fi
