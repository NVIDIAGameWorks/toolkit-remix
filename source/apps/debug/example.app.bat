@echo off
"%~dp0..\..\target-deps\kit_sdk_debug\_build\windows-x86_64\debug\omniverse-kit.exe" --config-path "%~dp0apps\example.app.json" %*
