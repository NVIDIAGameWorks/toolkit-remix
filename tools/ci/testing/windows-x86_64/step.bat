@echo off

if [%1]==[] (
  set target=alltests
) else (
  set target=%1
)

:: tests
call "%~dp0..\..\..\..\repo.bat" test -s %target%
if %errorlevel% neq 0 ( exit /b %errorlevel% )
