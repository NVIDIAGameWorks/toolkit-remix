@echo off

call "%~dp0dev\tools\packman\python" "%~dp0{omni_flux_validator_mass_core}\bin\cli.py" -x--merge-config="\"%~dp0{experience}\"" -x--/app/tokens/app="\"%~dp0apps\"" -k "\"%~dp0kit\kit.exe\"" %*
if %errorlevel% neq 0 ( goto Error )

:Success
exit /b 0

:Error
exit /b %errorlevel%
