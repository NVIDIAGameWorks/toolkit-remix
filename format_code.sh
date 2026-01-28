#!/bin/bash
set -e
SCRIPT_DIR=$(dirname ${BASH_SOURCE})
# TODO: revert back to `repo format` when it supports ruff
# source "$SCRIPT_DIR/repo.sh" format $@ || exit $?
"$SCRIPT_DIR/tools/packman/python.sh" "$SCRIPT_DIR/tools/utils/repo_format_with_ruff.py" "$@"
