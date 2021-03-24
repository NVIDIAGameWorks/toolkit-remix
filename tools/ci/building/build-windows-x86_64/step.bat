@echo off

:: Veify formatting
@REM call "%~dp0..\..\..\format_code.bat" --verify
@REM if %errorlevel% neq 0 ( exit /b %errorlevel% )

:: Full rebuild
call "%~dp0..\..\..\..\build.bat" -x -r
if %errorlevel% neq 0 ( exit /b %errorlevel% )

:: Docs
::call "%~dp0..\..\..\..\build_docs.bat" -c release
::if %errorlevel% neq 0 ( exit /b %errorlevel% )

:: Package all
call "%~dp0..\..\..\package.bat" -a -c release
if %errorlevel% neq 0 ( exit /b %errorlevel% )

:: publish artifacts to teamcity
echo ##teamcity[publishArtifacts '_build/packages']


