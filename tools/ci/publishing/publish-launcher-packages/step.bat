@echo off

call "%~dp0..\..\..\..\repo.bat" deploy_launcher
if %errorlevel% neq 0 ( exit /b %errorlevel% )


