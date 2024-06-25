#!/bin/bash

set -e

SCRIPT_DIR=$(dirname ${BASH_SOURCE})
cd "$SCRIPT_DIR"

exec "$SCRIPT_DIR/kit apps/omni.flux.app.asset_importer_cli.kit --no-window --exec cli.py $@"
