#!/bin/bash
set -e
SCRIPT_DIR=$(dirname ${BASH_SOURCE})
"$SCRIPT_DIR/tools/packman/python.sh" "$SCRIPT_DIR/tools/lint/python/run.py" $@ || exit $?
