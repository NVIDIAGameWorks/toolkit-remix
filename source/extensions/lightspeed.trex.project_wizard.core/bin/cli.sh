#!/bin/bash

set -e

SCRIPT_DIR=$(dirname ${BASH_SOURCE})
cd "$SCRIPT_DIR"

exec "$SCRIPT_DIR/kit apps/lightspeed.app.trex.project_wizard_cli.kit --no-window --exec cli.py $@"
