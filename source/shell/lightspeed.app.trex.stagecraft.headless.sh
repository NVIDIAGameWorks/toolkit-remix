#!/bin/bash

# Long-lived headless RTX Remix process for MCP + REST. No --exec and no
# --/app/quitAfter — the MCP server is the app loop. Excludes lightspeed.trex.app.setup
# (no skip flag exists; runtime exclusion is the documented path) and the splash exts
# (declarative .kit exclusion is unreliable for those due to lightspeed.dependencies'
# best-effort splash load).
SCRIPT_DIR=$(dirname ${BASH_SOURCE})
exec "$SCRIPT_DIR/kit/kit" "$SCRIPT_DIR/apps/lightspeed.app.trex.stagecraft.headless.kit" --no-window --/app/window/hideUi=1 --/exts/omni.kit.renderer.core/present/enabled=0 --/app/extensions/excluded/0='lightspeed.trex.app.setup' --/app/extensions/excluded/1='omni.kit.splash' --/app/extensions/excluded/2='omni.kit.window.splash' --/renderer/multiGpu/enabled=0 --/app/asyncRendering=0 --/app/file/ignoreUnsavedOnExit=1 "$@"
