@echo off

call "%~dp0dev\tools\packman\python" "%~dp0{omni_flux_service_documentation}\bin\cli.py" -x--/app/tokens/kit="\"%~dp0kit\"" %*
if %errorlevel% neq 0 ( goto Error )

:Success
exit /b 0

:Error
exit /b %errorlevel%
