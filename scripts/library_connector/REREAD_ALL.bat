@echo off
rem Double-click once: brings config.json up to date (it then reads each invoice's time), then reads every document
rem again, whatever its date, and sends it. The older invoices, read before the time was read, take their time;
rem the unchanged ones are skipped. Long (every document since the first): leave the window open until it ends.
rem If it says "giving up this run", double-click it again: the documents already sent are skipped.
title IMED ERP - read every invoice again (leave this window open until it ends)
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0update_config.ps1"
if errorlevel 1 (
  pause
  exit /b 1
)
set "PY="
for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*" "%ProgramFiles%\Python3*") do if exist "%%~D\python.exe" set "PY=%%~D\python.exe"
if not defined PY for /f "delims=" %%P in ('py -3 -c "import sys; print(sys.executable)" 2^>nul') do set "PY=%%P"
if not defined PY (
  echo FAILURE: Python is not installed: run SETUP_CONNECTOR first.
  pause
  exit /b 1
)
echo %date% %time% reading every document again...
"%PY%" tanmya_connector.py --config config.json --reread-all
if errorlevel 1 (
  echo FAILURE: not every document was sent. Double-click REREAD_ALL again.
) else (
  echo SUCCESS: every document was read again.
)
echo.
pause
