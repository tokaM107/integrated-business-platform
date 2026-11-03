@echo off
rem IMED ERP - library connector, first setup on the library PC. Double-click this file.
rem It installs the two Python packages the connector needs, checks config.json, then makes a DRY RUN:
rem it reads the library database (SELECT only) and writes batch_<time>.json next to this file. Nothing is sent.
title IMED ERP - library connector setup
cd /d "%~dp0"

echo [1/4] Python
rem Found where python.org installs it, so a PATH not yet refreshed (or the Microsoft Store alias) does not matter.
set "PY="
for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*" "%ProgramFiles%\Python3*") do if exist "%%~D\python.exe" set "PY=%%~D\python.exe"
if not defined PY for /f "delims=" %%P in ('py -3 -c "import sys; print(sys.executable)" 2^>nul') do set "PY=%%P"
if not defined PY (
  echo FAILURE: Python is not installed. Install it from python.org, then run this again.
  goto :end
)
"%PY%" --version
if errorlevel 1 (
  echo FAILURE: Python was found at %PY% but does not start.
  goto :end
)

echo.
echo [2/4] ODBC driver for SQL Server
powershell.exe -NoProfile -Command "$d = @(Get-OdbcDriver -Platform 64-bit | Where-Object { $_.Name -match 'ODBC Driver 1[78] for SQL Server' }); if ($d.Count) { $d | ForEach-Object { 'found: ' + $_.Name }; exit 0 } else { 'FAILURE: ODBC Driver 17 for SQL Server is not installed'; exit 1 }"
if errorlevel 1 goto :end

echo.
echo [3/4] Python packages (pyodbc, requests)
"%PY%" -m pip install --disable-pip-version-check --quiet pyodbc requests
if errorlevel 1 (
  echo FAILURE: the packages could not be installed. Is the internet working on this PC?
  goto :end
)
echo installed

echo.
echo [4/4] config.json check, then a dry run (reads the database, sends nothing)
"%PY%" tanmya_connector.py --config config.json --check
if errorlevel 1 (
  echo FAILURE: config.json is not ready, see the lines above.
  goto :end
)
"%PY%" tanmya_connector.py --config config.json --dry-run
if errorlevel 1 (
  echo FAILURE: the dry run stopped, see the lines above.
  goto :end
)
echo.
echo RESULT: SUCCESS - nothing was sent to the ERP.

:end
echo.
pause
