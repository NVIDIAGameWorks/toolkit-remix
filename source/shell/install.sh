#!/bin/bash

SCRIPT_DIR=$(dirname ${BASH_SOURCE})

# Warmup the Remix apps
"$SCRIPT_DIR/lightspeed.app.trex.warmup.sh"
"$SCRIPT_DIR/lightspeed.app.trex.stagecraft.warmup.sh"
"$SCRIPT_DIR/lightspeed.app.trex.ingestcraft.warmup.sh"
"$SCRIPT_DIR/lightspeed.app.trex.texturecraft.warmup.sh"
