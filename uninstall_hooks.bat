@echo off
rem Uninstall pre-commit hooks
rem Usage: uninstall_hooks.bat [-c]
rem   -c  Clean up the .venv directory after uninstalling hooks

echo Uninstalling pre-commit hooks...
echo.

set "VENV_DIR=%~dp0.venv"
set "CLEAN_VENV="

rem Parse arguments
if "%~1"=="-c" set "CLEAN_VENV=1"

if exist "%VENV_DIR%\Scripts\pre-commit.exe" (
    "%VENV_DIR%\Scripts\pre-commit.exe" uninstall
    "%VENV_DIR%\Scripts\pre-commit.exe" uninstall --hook-type pre-push
) else (
    echo pre-commit not found in .venv, skipping...
)

if defined CLEAN_VENV (
    echo.
    echo Cleaning up .venv directory...
    rmdir /s /q "%VENV_DIR%" 2>nul
    if exist "%VENV_DIR%" (
        echo WARNING: Could not fully remove .venv directory
    ) else (
        echo .venv directory removed.
    )
)

echo.
echo Hooks uninstalled.
echo.
if not defined CLEAN_VENV (
    echo To also remove the virtual environment, run: uninstall_hooks.bat -c
    echo Or delete the .venv directory manually.
    echo.
)
echo TIP: If you are uninstalling because you had issues, you can try reinstalling with:
echo.
echo   install_hooks.bat -f
echo.
echo This replaces existing hooks and often resolves conflicts with legacy hooks.
