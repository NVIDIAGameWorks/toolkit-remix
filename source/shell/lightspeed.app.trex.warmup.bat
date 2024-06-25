setlocal

:: Use half of available CPU cores for the warmup not to take all the resources from user's PC during installation
set /a TASKING_THREAD_CNT = %NUMBER_OF_PROCESSORS% / 2
call "%~dp0kit\kit.exe" "%%~dp0apps/lightspeed.app.trex.kit" --exec "open_stage.py \"%~dp0exts/lightspeed.trex.app.resources/data/usd_stages/BuiltInMaterials.usda\"" --/app/warmupMode=1 --no-window --/app/extensions/excluded/0='omni.kit.splash' --/app/extensions/excluded/1='omni.kit.window.splash' --/app/settings/persistent=0 --/app/settings/loadUserConfig=0 --/structuredLog/enable=0 --/app/hangDetector/enabled=0 --/crashreporter/skipOldDumpUpload=1 --/app/content/emptyStageOnStart=1 --/rtx/materialDb/syncLoads=1 --/omni.kit.plugin/syncUsdLoads=1 --/rtx/hydra/materialSyncLoads=1 --/app/asyncRendering=0 --/app/file/ignoreUnsavedOnExit=1 --/app/fastShutdown=1 --/renderer/multiGpu/enabled=0 --/app/quitAfter=10 --/plugins/carb.tasking.plugin/threadCount=%TASKING_THREAD_CNT% %*

:: Always succeed in case kit crashed or hanged
exit /b 0
