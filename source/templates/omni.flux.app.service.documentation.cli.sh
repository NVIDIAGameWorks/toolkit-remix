#!/bin/bash

set -e

SCRIPT_DIR=$(dirname ${BASH_SOURCE})

exec "$SCRIPT_DIR/dev/tools/packman/python.sh" "$SCRIPT_DIR/{omni_flux_service_documentation}/bin/cli.py" -x--/app/tokens/kit="$SCRIPT_DIR/kit" $@
