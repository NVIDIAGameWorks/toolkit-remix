@echo off
setlocal

set CARB_PROFILING_PYTHON=1
call "%~dp0kit\profile_startup.bat" "%~dp0apps\lightspeed.app.trex.kit" %*
set EXIT_CODE=%ERRORLEVEL%
if %EXIT_CODE% EQU 0 echo startup_profile.gz
exit /b %EXIT_CODE%
