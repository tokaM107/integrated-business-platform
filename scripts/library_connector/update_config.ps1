# Brings an installed config.json up to date without retyping its API key and secret (they stay as they are).
# Run through UPDATE_CONFIG.bat. Each change is applied once; running it again changes nothing.
#   4 Nov 2026: the stock documents' query also reads TxtOrderTime (the time the cashier saved the invoice).
#   9 Nov 2026: the lines' query also reads each item's category (the "item group" of Tanmya's daily sales
#               report by group) and the doctor's share of the line (DoctorValueAFDiscount).
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
if ($text -notmatch 'TxtProductCategoryName') {
	$old = "d.TxtDoctorName FROM dbo.TblRefStockSub s LEFT JOIN dbo.TblProductInfo p ON p.TxtProductCode = s.TxtProductCodeRefStockSub LEFT JOIN dbo.TblDoctorInfo d ON d.TxtDoctorCode = s.DoctorCode WHERE"
	$add = "d.TxtDoctorName, s.DoctorValueAFDiscount, p.TxtProductCategoryCode, pc.TxtProductCategoryName FROM dbo.TblRefStockSub s LEFT JOIN dbo.TblProductInfo p ON p.TxtProductCode = s.TxtProductCodeRefStockSub LEFT JOIN dbo.TblDoctorInfo d ON d.TxtDoctorCode = s.DoctorCode LEFT JOIN dbo.TblProductCategoryInfo pc ON pc.TxtProductCategoryCode = p.TxtProductCategoryCode WHERE"
	$new = $text.Replace($old, $add)
	if ($new -eq $text) { Write-Host "FAILURE: the lines query in config.json is not the expected one; nothing was changed"; exit 1 }
	$text = $new
	$changed++
	Write-Host "added: each item's group (category) and the doctor's share"
}
if ($changed) {
	Copy-Item $cfg ($cfg + ".bak") -Force
	[IO.File]::WriteAllText($cfg, $text, (New-Object Text.UTF8Encoding $false))
	Write-Host "SUCCESS: config.json updated (the old one kept as config.json.bak)"
} else {
	Write-Host "SUCCESS: config.json was already up to date"
}
