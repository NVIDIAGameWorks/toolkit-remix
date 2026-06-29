#!/bin/bash

SCRIPT_DIR=$(dirname ${BASH_SOURCE})
export CARB_PROFILING_PYTHON=1
"$SCRIPT_DIR/kit/profile_startup.sh" "$SCRIPT_DIR/apps/lightspeed.app.trex.kit" "$@"
EXIT_CODE=$?
if [ $EXIT_CODE -eq 0 ]; then
    echo startup_profile.gz
fi
exit $EXIT_CODE
