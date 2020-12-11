@echo off

:: Pass example root folder so that we can find path to config in python
set EXAMPLE_ROOT=%~dp0

"%~dp0..\..\kit_release\_build\windows-x86_64\release\python.bat" "%~dp0/pythonapps/example.py" %*
