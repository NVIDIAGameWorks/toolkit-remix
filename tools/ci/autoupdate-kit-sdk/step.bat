@echo off

call "%~dp0..\..\..\repo.bat" kit_autoupdate %*
if %errorlevel% neq 0 ( exit /b %errorlevel% )
