@echo off

call "%~dp0dev\tools\packman\python" "%~dp0tools\migrations\migrations_cli.py" %*

if %errorlevel% neq 0 ( goto Error )

:Success
exit /b 0

:Error
exit /b %errorlevel%
