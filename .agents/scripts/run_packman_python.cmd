:; unset PYTHONHOME PYTHONPATH; SCRIPT_DIR=$(dirname "$0"); ROOT=$(cd "$SCRIPT_DIR/../.." && pwd) || exit $?; cd "$ROOT" || exit $?; exec "$ROOT/tools/packman/python.sh" "$@"
@echo off
setlocal
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "PYTHONHOME="
set "PYTHONPATH="
set "ROOT=%~dp0..\.."
cd /d "%ROOT%" || exit /b 1

call "%ROOT%\tools\packman\python.bat" %*
exit /b %ERRORLEVEL%
