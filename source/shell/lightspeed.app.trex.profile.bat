@echo off
setlocal

set CARB_PROFILING_PYTHON=1
call "%~dp0lightspeed.app.trex.bat" --enable omni.kit.profiler.tracy --enable omni.kit.profiler.window --/app/profilerBackend=[cpu,tracy] %*
exit /b %ERRORLEVEL%
