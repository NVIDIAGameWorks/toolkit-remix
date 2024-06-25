@echo off
setlocal
call "%~dp0..\..\..\kit\kit.exe" "%%~dp0../apps/omni.flux.app.validator.kit" --exec "%~dp0omni.flux.app.validator.py" %*

if %errorlevel% neq 0 ( goto Error )

:Success
exit /b 0

:Error
exit /b %errorlevel%
