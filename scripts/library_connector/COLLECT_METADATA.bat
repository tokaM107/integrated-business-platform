@echo off
rem IMED ERP - library metadata collector. Double-click this file. It only READS the database and makes one ZIP on the Desktop.
title IMED ERP - library metadata collector
echo Starting... please wait, do not close this window.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0collect_metadata.ps1"
echo.
if errorlevel 1 (echo RESULT: FAILURE - read the lines above, then bring the ZIP anyway.) else (echo RESULT: SUCCESS - bring the ZIP file named above.)
echo.
pause
