@echo off

call "%~dp0tools\packman\python.bat" %~dp0tools\repoman\build.py %*
if %errorlevel% neq 0 ( goto Error )

call "%~dp0tools\gather_licenses.bat
if %errorlevel% neq 0 ( goto Error)

:Success
exit /b 0

:Error
exit /b %errorlevel%
