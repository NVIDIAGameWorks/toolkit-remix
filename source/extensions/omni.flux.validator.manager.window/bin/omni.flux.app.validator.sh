#!/bin/bash

set -e

SCRIPT_DIR=$(dirname ${BASH_SOURCE})
cd "$SCRIPT_DIR"

exec "$SCRIPT_DIR/../../../kit" "$SCRIPT_DIR/../apps/omni.flux.app.validator.kit --exec omni.flux.app.validator.py" $@
