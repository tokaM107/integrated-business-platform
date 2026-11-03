@echo off
rem Double-click: asks for the ERP API key and secret and saves them in config.json.
title IMED ERP - save the API key
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0set_keys.ps1"
echo.
pause
