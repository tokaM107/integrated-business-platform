@echo off
rem Double-click: brings config.json up to date; the API key and secret are kept.
title IMED ERP - update the connector settings
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0update_config.ps1"
echo.
pause
