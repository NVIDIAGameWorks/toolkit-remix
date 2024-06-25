#!/bin/bash
set -e
SCRIPT_DIR=$(dirname ${BASH_SOURCE})
source "$SCRIPT_DIR/repo.sh" auto_update_deps $@ || exit $?
