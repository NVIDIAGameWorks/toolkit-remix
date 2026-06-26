:; SCRIPT_DIR=$(dirname "$0"); ROOT=$(cd "$SCRIPT_DIR/../.." 2>/dev/null; pwd); cd "$ROOT"; exec "$ROOT/tools/packman/python.sh" "$@"
@echo off
setlocal
set "ROOT=%~dp0..\.."
cd /d "%ROOT%"

call "%ROOT%\tools\packman\python.bat" %*
exit /b %ERRORLEVEL%
