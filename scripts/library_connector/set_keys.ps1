# Puts the ERP connector user's API key and secret into config.json (next to this file), in place of the
# placeholders. Run through SET_KEYS.bat. The secret is not printed.
$cfg = Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) "config.json"
if (-not (Test-Path $cfg)) { Write-Host "FAILURE: config.json is not in this folder"; exit 1 }
$text = [IO.File]::ReadAllText($cfg, [Text.Encoding]::UTF8)
if ($text -notmatch '"api_key": "<' -and $text -notmatch '"api_secret": "<') {
	Write-Host "config.json already has a key and a secret. To change them, put a fresh copy of config.json here first."
	exit 1
}
Write-Host ""
$key = (Read-Host "Paste the API Key (right-click to paste), then press Enter").Trim().Trim('"')
$secret = (Read-Host "Paste the API Secret (right-click to paste), then press Enter").Trim().Trim('"')
if ($key -notmatch '^[A-Za-z0-9]+$' -or $secret -notmatch '^[A-Za-z0-9]+$') {
	Write-Host "FAILURE: a key or secret is letters and digits only; something else was pasted. Nothing was changed."
	exit 1
}
$text = $text -replace '"api_key": "<[^"]*"', ('"api_key": "' + $key + '"')
$text = $text -replace '"api_secret": "<[^"]*"', ('"api_secret": "' + $secret + '"')
[IO.File]::WriteAllText($cfg, $text, (New-Object Text.UTF8Encoding $false))
Write-Host ""
Write-Host "SUCCESS: key and secret saved in config.json"
