#!/bin/bash
set -e
SCRIPT_DIR=$(dirname ${BASH_SOURCE})
"$SCRIPT_DIR/../../target-deps/kit_sdk_debug/_build/linux-x86_64/debug/omniverse-kit" "$SCRIPT_DIR/apps/example.app.json" $@
