setlocal

:: Warmup the Remix apps
call "%~dp0lightspeed.app.trex.warmup.bat"
call "%~dp0lightspeed.app.trex.stagecraft.warmup.bat"
call "%~dp0lightspeed.app.trex.ingestcraft.warmup.bat"

exit /b 0
