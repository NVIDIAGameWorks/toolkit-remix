@echo off

call "%~dp0build.bat" -g %*
if errorlevel 1 ( goto Error )

:Success
exit /b 0

:Error
exit /b %errorlevel%