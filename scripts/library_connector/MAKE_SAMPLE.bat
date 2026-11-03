@echo off
rem Double-click: writes sample.json (5 documents from the newest dry run), small enough to copy. Sends nothing.
title IMED ERP - library sample
cd /d "%~dp0"
set "PY="
for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*" "%ProgramFiles%\Python3*") do if exist "%%~D\python.exe" set "PY=%%~D\python.exe"
if not defined PY for /f "delims=" %%P in ('py -3 -c "import sys; print(sys.executable)" 2^>nul') do set "PY=%%P"
if not defined PY (
  echo FAILURE: Python is not installed.
  goto :end
)
"%PY%" make_sample.py
if errorlevel 1 (echo FAILURE: see the lines above.) else (echo RESULT: SUCCESS - copy sample.json)
:end
echo.
pause
