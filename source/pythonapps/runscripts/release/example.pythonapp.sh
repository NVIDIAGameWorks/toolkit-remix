#!/bin/bash
set -e

SCRIPT_DIR=$(dirname ${BASH_SOURCE})

# Pass example root folder so that we can find path to config in python
export EXAMPLE_ROOT=${SCRIPT_DIR}

"./$SCRIPT_DIR/../../target-deps/kit_sdk_release/_build/linux-x86_64/release/python.sh" "$SCRIPT_DIR/pythonapps/example.py" $@
