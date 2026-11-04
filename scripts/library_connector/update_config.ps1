# Brings an installed config.json up to date without retyping its API key and secret (they stay as they are).
# Run through UPDATE_CONFIG.bat. Each change is applied once; running it again changes nothing.
#   4 Nov 2026: the stock documents' query also reads TxtOrderTime (the time the cashier saved the invoice).
$cfg = Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) "config.json"
if (-not (Test-Path $cfg)) { Write-Host "FAILURE: config.json is not in this folder"; exit 1 }
$text = [IO.File]::ReadAllText($cfg, [Text.Encoding]::UTF8)
$changed = 0
if ($text -notmatch 'h\.TxtOrderTime') {
	$new = $text.Replace("h.TxtUserCodeRefStock FROM dbo.TblRefStockHead", "h.TxtUserCodeRefStock, h.TxtOrderTime FROM dbo.TblRefStockHead")
	if ($new -eq $text) { Write-Host "FAILURE: the stock query in config.json is not the expected one; nothing was changed"; exit 1 }
	$text = $new
	$changed++
	Write-Host "added: the invoice time (TxtOrderTime)"
}
if ($changed) {
	Copy-Item $cfg ($cfg + ".bak") -Force
	[IO.File]::WriteAllText($cfg, $text, (New-Object Text.UTF8Encoding $false))
	Write-Host "SUCCESS: config.json updated (the old one kept as config.json.bak)"
} else {
	Write-Host "SUCCESS: config.json was already up to date"
}
