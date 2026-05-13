@echo off
setlocal
for /f "delims=" %%I in ('git rev-parse --show-toplevel 2^>nul') do set "ROOT=%%I"
if not defined ROOT set "ROOT=%CD%"
cd /d "%ROOT%"

:MAKE_TEMP_DIR
set "TMPDIR_RUNNER=%TEMP%\lightspeed-packman-python-%RANDOM%-%RANDOM%-%RANDOM%"
mkdir "%TMPDIR_RUNNER%" > nul 2>&1
if errorlevel 1 goto MAKE_TEMP_DIR

set "OUT=%TMPDIR_RUNNER%\out"
set "ERR=%TMPDIR_RUNNER%\err"
set "CODE=%TMPDIR_RUNNER%\code"
set "BOOT=%TMPDIR_RUNNER%\boot"

call "%ROOT%\tools\packman\python.bat" "%ROOT%\.agents\scripts\packman_python_entry.py" --stdout-file "%OUT%" --stderr-file "%ERR%" --exit-code-file "%CODE%" -- %* > "%BOOT%" 2>&1
set "PM_CODE=%ERRORLEVEL%"

if exist "%OUT%" type "%OUT%"
if exist "%ERR%" type "%ERR%" 1>&2
if exist "%CODE%" goto READ_SCRIPT_CODE
if exist "%BOOT%" type "%BOOT%" 1>&2
set "SCRIPT_CODE=%PM_CODE%"
goto FINISH

:READ_SCRIPT_CODE
set "SCRIPT_CODE=1"
set /p SCRIPT_CODE=<"%CODE%"
if not defined SCRIPT_CODE set "SCRIPT_CODE=1"
echo(%SCRIPT_CODE%| findstr /r "^[0-9][0-9]*$" > nul || set "SCRIPT_CODE=1"

:FINISH
rmdir /s /q "%TMPDIR_RUNNER%" > nul 2>&1
exit /b %SCRIPT_CODE%
