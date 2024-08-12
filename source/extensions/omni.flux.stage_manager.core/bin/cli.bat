@echo off

call "%~dp0..\..\..\dev\tools\packman\python" %~dp0cli.py %*
if %errorlevel% neq 0 ( goto Error )

:Success
exit /b 0

:Error
exit /b %errorlevel%
