#!/bin/bash

set -e

SCRIPT_DIR=$(dirname ${BASH_SOURCE})

exec "$SCRIPT_DIR/dev/tools/packman/python.sh" "$SCRIPT_DIR/tools/migrations/migrations_cli.py" $@
