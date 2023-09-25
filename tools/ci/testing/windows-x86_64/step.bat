@echo off

:: tests
call "%~dp0..\..\..\..\repo.bat" test -s alltests
if %errorlevel% neq 0 ( exit /b %errorlevel% )
