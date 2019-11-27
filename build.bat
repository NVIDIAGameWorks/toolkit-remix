@echo off

call "%~dp0tools\packman\python" %~dp0tools\repoman\build.py %*
if errorlevel 1 ( goto Error )

:Success
exit /b 0

:Error
exit /b %errorlevel%
