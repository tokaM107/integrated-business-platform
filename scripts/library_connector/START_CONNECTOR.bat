@echo off
rem For a library PC where Task Scheduler and the Startup folder are denied (an antivirus or a policy): double-click
rem after each start of the PC and minimize the window. The connector runs now and every 10 minutes while the
rem window stays open; closing it stops the connector (nothing is lost: the next start catches up).
title IMED ERP - library connector (minimize this window, do not close it)
cd /d "%~dp0"
set "PY="
for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*" "%ProgramFiles%\Python3*") do if exist "%%~D\python.exe" set "PY=%%~D\python.exe"
if not defined PY for /f "delims=" %%P in ('py -3 -c "import sys; print(sys.executable)" 2^>nul') do set "PY=%%P"
if not defined PY (
  echo FAILURE: Python is not installed: run SETUP_CONNECTOR first.
  pause
  exit /b 1
)
echo The connector runs every 10 minutes while this window is open. Minimize it; do not close it.
:loop
echo.
echo %date% %time% sending...
"%PY%" tanmya_connector.py --config config.json >> connector.log 2>&1
powershell.exe -NoProfile -Command "Get-Content -Path connector.log -Tail 3 -Encoding UTF8"
echo next run in 10 minutes
timeout /t 600 /nobreak >nul
goto loop
