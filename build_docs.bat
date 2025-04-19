@echo off
call "%~dp0tools\\packman\\python.bat" -m pip install -r "%~dp0requirements.docs.txt"
call "%~dp0repo" docs %*
