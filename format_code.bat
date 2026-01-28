@echo off
rem call "%~dp0repo" format %*  # TODO: revert back to `repo format` when it supports ruff
call "%~dp0tools\packman\python.bat" "%~dp0tools\utils\repo_format_with_ruff.py" %*
