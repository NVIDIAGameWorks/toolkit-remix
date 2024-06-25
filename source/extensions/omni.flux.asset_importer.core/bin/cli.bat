@echo off
setlocal
set args=%*
echo "%~dp0..\..\..\kit\kit.exe" "%~dp0..\apps\omni.flux.app.asset_importer_cli.kit" --no-window --exec "%~dp0cli.py %args%"
call "%~dp0..\..\..\kit\kit.exe" "%~dp0..\apps\omni.flux.app.asset_importer_cli.kit" --no-window --exec "%~dp0cli.py %args%"

if %errorlevel% neq 0 ( goto Error )

:Success
exit /b 0

:Error
exit /b %errorlevel%
