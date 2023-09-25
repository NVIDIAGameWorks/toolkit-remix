#!/bin/bash

SCRIPT_DIR=$(dirname ${BASH_SOURCE})
# Pull dependencies
"$SCRIPT_DIR/pull_kit_sdk.sh"
"$SCRIPT_DIR/pull_dependencies.sh"

# Warmup the Remix apps
"$SCRIPT_DIR/lightspeed.app.trex.warmup.sh"
"$SCRIPT_DIR/lightspeed.app.trex.stagecraft.warmup.sh"
"$SCRIPT_DIR/lightspeed.app.trex.ingestcraft.warmup.sh"
"$SCRIPT_DIR/lightspeed.app.trex.texturecraft.warmup.sh"
