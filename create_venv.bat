@echo off
rem Create a Python virtual environment using packman's Python

set "VENV_DIR=%~dp0.venv"

if exist "%VENV_DIR%\Scripts\python.exe" (
    echo Virtual environment already exists at %VENV_DIR%
    exit /b 0
)

echo Creating virtual environment...
call "%~dp0tools\packman\python.bat" -m venv "%VENV_DIR%"
if errorlevel 1 (
    echo ERROR: Failed to create virtual environment
    exit /b 1
)

echo.
echo Virtual environment created at %VENV_DIR%
echo Activate with: .venv\Scripts\activate
