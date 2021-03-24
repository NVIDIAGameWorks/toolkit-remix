#!/bin/bash
set -e
SCRIPT_DIR=$(dirname ${BASH_SOURCE})
source "$SCRIPT_DIR/dev/packman/python.sh" "$SCRIPT_DIR/pull_kit_sdk.py" -c release $@ || exit $?
