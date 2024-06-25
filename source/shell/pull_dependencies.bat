setlocal

:: Download the install-time dependencies
call "%~dp0dev\tools\packman\packman" pull "%~dp0dev\deps\install-deps.packman.xml" %*

exit /b 0
