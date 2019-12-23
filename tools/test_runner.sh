#!/bin/bash
set -e
SCRIPT_DIR=$(dirname ${BASH_SOURCE})
source "$SCRIPT_DIR/packman/python.sh" "$SCRIPT_DIR/repoman/test_runner.py" $@ || exit $?
