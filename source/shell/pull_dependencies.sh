#!/bin/bash

# Download the install-time dependencies
SCRIPT_DIR=$(dirname ${BASH_SOURCE})
exec "$SCRIPT_DIR/dev/tools/packman/packman" pull "$SCRIPT_DIR/dev/deps/install-deps.packman.xml" "$@"

