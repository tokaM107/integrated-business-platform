# Registers the connector in Windows Task Scheduler on a library PC: every 10 minutes, as the Windows user that
# runs the library program (its login is what SQL Server trusts), whether or not anyone is logged in.
#
#   Right-click > Run with PowerShell (as that user), from the connector's folder, after:
#     1. python -m pip install pyodbc requests        (Python 3.9+ from python.org, "Add to PATH" ticked)
#     2. config.json filled from this PC's metadata ZIP; python tanmya_connector.py --config config.json --check
#     3. a dry run:  python tanmya_connector.py --config config.json --dry-run   (writes batch_*.json, posts nothing)
#     4. the first live batch by hand, checked in the ERP (Integration Status)
#
#   .\install_task.ps1               registers (or replaces) the task "IMED Library Connector"
#   .\install_task.ps1 -Remove       removes it
param([switch]$Remove, [string]$TaskName = "IMED Library Connector", [int]$Minutes = 10)

$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $python) { Write-Host "python not found on PATH: install Python 3.9+ first"; exit 1 }
if ($Remove) { schtasks /Delete /TN "$TaskName" /F; exit $LASTEXITCODE }
if (-not (Test-Path (Join-Path $here "config.json"))) { Write-Host "config.json is missing next to this script"; exit 1 }
& $python (Join-Path $here "tanmya_connector.py") --config (Join-Path $here "config.json") --check
if ($LASTEXITCODE -ne 0) { Write-Host "config.json is not ready (see the lines above); the task was not installed"; exit 2 }

$log = Join-Path $here "connector.log"
$cmd = "cmd /c `"cd /d `"$here`" && `"$python`" tanmya_connector.py --config config.json >> `"$log`" 2>&1`""
schtasks /Create /TN "$TaskName" /SC MINUTE /MO $Minutes /TR $cmd /F /RL LIMITED /RU "$env:USERDOMAIN\$env:USERNAME" /IT
if ($LASTEXITCODE -eq 0) {
    Write-Host "installed: '$TaskName' every $Minutes minutes as $env:USERNAME; log: $log"
    Write-Host "check it: schtasks /Query /TN `"$TaskName`" /V /FO LIST"
}
exit $LASTEXITCODE
