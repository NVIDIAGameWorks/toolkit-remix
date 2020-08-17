@echo off

pushd "%~dp0.."


if exist _build\PACKAGE-LICENSES (
    del /Q /F _build\PACKAGE-LICENSES\* > nul 2>&1
)

call "%~dp0..\tools\packman\python.bat" "%~dp0repoman\licensing.py" gather -d "%cd%" -p "deps\target-deps.packman.xml" --platform "windows-x86_64" %LICENSING_OPTIONS% %*
if %errorlevel% neq 0 ( goto End )

:End
popd
