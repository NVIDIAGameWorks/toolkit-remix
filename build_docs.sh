#!/bin/bash
set -e
SCRIPT_DIR=$(dirname ${BASH_SOURCE})
source "$SCRIPT_DIR/tools/packman/python.sh" -m pip install -r "$SCRIPT_DIR/requirements.docs.txt"
source "$SCRIPT_DIR/repo.sh" docs $@ || exit $?
