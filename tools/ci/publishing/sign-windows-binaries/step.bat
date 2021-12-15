@echo off

call "%~dp0..\..\..\packman\python" "%~dp0..\..\..\repoman\sign_archive.py"
if %errorlevel% neq 0 ( exit /b %errorlevel% )


