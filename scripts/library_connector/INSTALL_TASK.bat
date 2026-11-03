@echo off
rem Double-click, as the Windows user that opens the library program: registers the connector to run every
rem 10 minutes (Task Scheduler task "IMED Library Connector"). Its first run sends every document; later runs only
rem the new and changed ones. Log: connector.log in this folder.
title IMED ERP - install the library connector task
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0install_task.ps1"
if errorlevel 1 (echo RESULT: FAILURE - read the lines above.) else (echo RESULT: SUCCESS - the connector now runs every 10 minutes.)
echo.
pause
