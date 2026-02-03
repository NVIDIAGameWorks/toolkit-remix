@echo off
rem Install pre-commit hooks for formatting (on commit) and linting (on push)
rem Usage: install_hooks.bat [-f]
rem   -f  Force install, replacing any existing hooks

set "VENV_DIR=%~dp0.venv"
set "FORCE_FLAG="

rem Parse arguments
if "%~1"=="-f" set "FORCE_FLAG=-f"

if defined FORCE_FLAG (
    echo Performing clean install of pre-commit hooks...
) else (
    echo Installing pre-commit hooks...
)
echo.

rem Create venv if it doesn't exist
call "%~dp0create_venv.bat"
if errorlevel 1 exit /b 1

rem Install pre-commit into the venv
"%VENV_DIR%\Scripts\pip.exe" install pre-commit==4.0.1
if errorlevel 1 (
    echo ERROR: Failed to install pre-commit
    exit /b 1
)

rem Install the hooks
"%VENV_DIR%\Scripts\pre-commit.exe" install %FORCE_FLAG%
if errorlevel 1 (
    echo ERROR: Failed to install pre-commit hook
    exit /b 1
)

"%VENV_DIR%\Scripts\pre-commit.exe" install --hook-type pre-push %FORCE_FLAG%
if errorlevel 1 (
    echo ERROR: Failed to install pre-push hook
    exit /b 1
)

echo.
echo Hooks installed successfully!
echo   - Commit: auto-format with ruff
echo   - Push: lint check with ruff
echo.
echo Skip with: git commit --no-verify / git push --no-verify

if not defined FORCE_FLAG (
    echo.
    echo TIP: If your hooks fail to run ^(e.g. pre-push errors^), try reinstalling with:
    echo.
    echo   install_hooks.bat -f
    echo.
    echo This replaces existing hooks and often resolves conflicts with legacy hooks.
)
