@echo off
"%~dp0..\..\target-deps\kit_sdk_release\_build\windows-x86_64\release\omniverse-kit.exe" --config-path "%~dp0apps\example.app.json" %*
