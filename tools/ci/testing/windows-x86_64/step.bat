@echo off

:: tests
call "%~dp0..\..\..\..\repo.bat" test
if %errorlevel% neq 0 ( exit /b %errorlevel% )

