@echo off
setlocal
if not defined PYTHONNOUSERSITE (
    set PYTHONNOUSERSITE=1
)
if not defined PYTHONUNBUFFERED (
    set PYTHONUNBUFFERED=1
)
set "DOCS_PYTHON=%~dp0_build\target-deps\python\python.exe"
if not exist "%DOCS_PYTHON%" (
    echo Docs Python not found at "%DOCS_PYTHON%". Run build.bat before build_docs.bat.
    exit /b 1
)
set "PM_PYTHON_EXT=%DOCS_PYTHON%"
call "%DOCS_PYTHON%" -m pip install -r "%~dp0requirements.docs.txt"
if %errorlevel% neq 0 ( exit /b %errorlevel% )
call "%~dp0repo" docs %*
