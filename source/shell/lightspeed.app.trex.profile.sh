#!/bin/bash

SCRIPT_DIR=$(dirname ${BASH_SOURCE})
export CARB_PROFILING_PYTHON=1
exec "$SCRIPT_DIR/kit/kit" "$SCRIPT_DIR/apps/lightspeed.app.trex.kit" --enable omni.kit.profiler.tracy --enable omni.kit.profiler.window --/app/profilerBackend=[cpu,tracy] "$@"
