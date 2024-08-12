#!/bin/bash

set -e

SCRIPT_DIR=$(dirname ${BASH_SOURCE})
cd "$SCRIPT_DIR"

exec "$SCRIPT_DIR/../../../dev/tools/packman/python.sh" cli.py $@
