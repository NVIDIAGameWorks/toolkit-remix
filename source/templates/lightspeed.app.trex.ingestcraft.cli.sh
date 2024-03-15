#!/bin/bash

set -e

SCRIPT_DIR=$(dirname ${BASH_SOURCE})

exec "$SCRIPT_DIR/dev/tools/packman/python.sh" "$SCRIPT_DIR/{omni_flux_validator_mass_core}/bin/cli.py" -x--merge-config="$SCRIPT_DIR/{experience}" -x--/app/tokens/app="$SCRIPT_DIR/apps" $@
