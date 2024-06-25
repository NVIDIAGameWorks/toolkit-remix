@echo off
setlocal
set args=%*
call "%~dp0..\..\..\kit\kit.exe" "%~dp0..\apps\lightspeed.app.trex.project_packaging_cli.kit" --no-window --exec "%~dp0cli.py %args%"

if %errorlevel% neq 0 ( goto Error )

:Success
exit /b 0

:Error
exit /b %errorlevel%
