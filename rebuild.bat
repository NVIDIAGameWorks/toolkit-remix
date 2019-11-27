@echo off


call build.bat --rebuild %*
if errorlevel 1 ( goto Error )


:Success
exit /b 0


:Error
exit /b %errorlevel%
