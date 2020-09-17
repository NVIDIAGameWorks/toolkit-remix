@echo off

:: Pass example root folder so that we can find path to config in python
set EXAMPLE_ROOT=%~dp0

"%~dp0..\..\target-deps\kit_sdk_debug\_build\windows-x86_64\debug\python.bat" "%~dp0/pythonapps/example.py" %*
