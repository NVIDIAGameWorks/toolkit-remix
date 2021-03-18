@echo off

:: pull kit
call "%~dp0..\..\..\..\tools\pull_kit_sdk.bat" -c release
if %errorlevel% neq 0 ( exit /b %errorlevel% )

:: tests
call "%~dp0..\..\..\..\repo.bat" test --config release
if %errorlevel% neq 0 ( exit /b %errorlevel% )

