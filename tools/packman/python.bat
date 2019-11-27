@echo off
setlocal

call "%~dp0\packman" --version > nul
set "PYTHONPATH=%PM_MODULE_DIR%;%PYTHONPATH%"
"%PM_PYTHON%" -u %*
