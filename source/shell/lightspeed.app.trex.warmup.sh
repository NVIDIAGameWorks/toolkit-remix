#!/bin/bash

# Use half of available CPU cores for the warmup not to tak all the resources from user's PC during installation
TASKING_THREAD_CNT=$(($(nproc)/2))

SCRIPT_DIR=$(dirname ${BASH_SOURCE})
exec "$SCRIPT_DIR/kit/kit" "$SCRIPT_DIR/apps/lightspeed.app.trex.kit" --/app/warmupMode=1 --no-window --/app/extensions/excluded/0='omni.omni.kit.welcome.window' --/app/settings/persistent=0 --/app/settings/loadUserConfig=0 --/structuredLog/enable=0 --/app/hangDetector/enabled=0 --/crashreporter/skipOldDumpUpload=1 --/app/content/emptyStageOnStart=1 --/rtx/materialDb/syncLoads=1 --/omni.kit.plugin/syncUsdLoads=1 --/rtx/hydra/materialSyncLoads=1 --/app/asyncRendering=0 --/app/file/ignoreUnsavedOnExit=1 --/app/fastShutdown=1 --/renderer/multiGPU/enabled=0 --/app/quitAfter=10 --/plugins/carb.tasking.plugin/threadCount=$TASKING_THREAD_CNT "$@"

# Always succeed in case kit crashed or hanged
exit 0
