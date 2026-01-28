@echo off
rem Uninstall pre-commit hooks

echo Uninstalling pre-commit hooks...
echo.

set "VENV_DIR=%~dp0.venv"

if exist "%VENV_DIR%\Scripts\pre-commit.exe" (
    "%VENV_DIR%\Scripts\pre-commit.exe" uninstall
    "%VENV_DIR%\Scripts\pre-commit.exe" uninstall --hook-type pre-push
) else (
    echo pre-commit not found in .venv, skipping...
)

echo.
echo Hooks uninstalled.
echo.
echo To remove the virtual environment, delete the .venv folder.
