@echo off

call "%~dp0..\..\..\generate_build_number.bat"
if %errorlevel% neq 0 ( exit /b %errorlevel% )


