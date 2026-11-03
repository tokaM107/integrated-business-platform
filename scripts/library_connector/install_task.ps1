# Makes the connector run every 10 minutes on a library PC, hidden (no window over the library program), as the
# Windows user that runs the library program (its login is what SQL Server trusts). Run it through INSTALL_TASK.bat,
# from the connector's folder, after SETUP_CONNECTOR.bat succeeded (Python, the ODBC driver, config.json, a dry run).
#
#   1. a Task Scheduler task "IMED Library Connector" (Register-ScheduledTask), every 10 minutes while the user is
#      logged in;
#   2. if Task Scheduler is not allowed on this PC (some antivirus or policies deny it), a file in the user's Startup
#      folder that starts the connector at log-in and runs it every 10 minutes, and it is started right away.
# Either way the runs go through run_connector.vbs (written here, with this PC's Python), one at a time, and append
# to connector.log in this folder.
#
#   .\install_task.ps1               installs (or replaces)
#   .\install_task.ps1 -Remove       removes both
param([switch]$Remove, [string]$TaskName = "IMED Library Connector", [int]$Minutes = 10)
$ErrorActionPreference = "Stop"

$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$vbs = Join-Path $here "run_connector.vbs"
$startup = Join-Path ([Environment]::GetFolderPath("Startup")) "IMED Library Connector.vbs"

if ($Remove) {
	try { Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction Stop; Write-Host "task removed" } catch { Write-Host "no task to remove" }
	if (Test-Path $startup) { Remove-Item $startup -Force; Write-Host "Startup entry removed (a loop already running stops at the next log-off)" }
	exit 0
}

# Where python.org installs it first: a PATH not yet refreshed, or the Microsoft Store alias, does not matter then.
$python = @(Get-ChildItem -Path "$env:LOCALAPPDATA\Programs\Python\Python3*\python.exe", "$env:ProgramFiles\Python3*\python.exe" -ErrorAction SilentlyContinue | Select-Object -ExpandProperty FullName) | Select-Object -Last 1
if (-not $python) { $python = (Get-Command python -ErrorAction SilentlyContinue | Where-Object { $_.Source -notmatch 'WindowsApps' }).Source }
if (-not $python) { Write-Host "FAILURE: Python not found: run SETUP_CONNECTOR.bat first"; exit 1 }
if (-not (Test-Path (Join-Path $here "config.json"))) { Write-Host "FAILURE: config.json is missing next to this script"; exit 1 }
& $python (Join-Path $here "tanmya_connector.py") --config (Join-Path $here "config.json") --check
if ($LASTEXITCODE -ne 0) { Write-Host "FAILURE: config.json is not ready (see the lines above); nothing was installed"; exit 2 }

# One run, hidden, waiting for it to end; with the argument "loop", again every $Minutes minutes, for ever.
$cmd = "cmd /c cd /d """"$here"""" && """"$python"""" tanmya_connector.py --config config.json >> connector.log 2>&1"
@(
	"' Written by install_task.ps1: runs the IMED library connector hidden. With the argument loop: every $Minutes minutes.",
	"Set sh = CreateObject(""WScript.Shell"")",
	"Do",
	"  sh.Run ""$cmd"", 0, True",
	"  If WScript.Arguments.Count = 0 Then Exit Do",
	"  WScript.Sleep $($Minutes * 60000)",
	"Loop"
) | Set-Content -Path $vbs -Encoding ASCII

$how = $null
try {
	$action = New-ScheduledTaskAction -Execute "wscript.exe" -Argument """$vbs""" -WorkingDirectory $here
	$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes $Minutes) -RepetitionDuration (New-TimeSpan -Days 3650)
	$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 3)
	$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited
	Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force -ErrorAction Stop | Out-Null
	Get-ScheduledTask -TaskName $TaskName -ErrorAction Stop | Out-Null
	if (Test-Path $startup) { Remove-Item $startup -Force }
	$how = "Task Scheduler task '$TaskName'"
} catch {
	Write-Host "Task Scheduler is not allowed here ($($_.Exception.Message.Split([char]10)[0])); using the Startup folder instead"
}
if (-not $how) {
	try {
		"CreateObject(""WScript.Shell"").Run ""wscript.exe """"$vbs"""" loop"", 0, False" | Set-Content -Path $startup -Encoding ASCII
		Start-Process -FilePath "wscript.exe" -ArgumentList """$vbs"" loop" -WorkingDirectory $here
		$how = "the Startup folder ($startup), started now"
	} catch {
		Write-Host "FAILURE: the Startup folder could not be used either: $($_.Exception.Message.Split([char]10)[0])"
		exit 1
	}
}
Write-Host "installed: every $Minutes minutes, hidden, as $env:USERNAME, through $how"
Write-Host "log: $(Join-Path $here 'connector.log')"
exit 0
