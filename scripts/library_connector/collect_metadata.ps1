# Collects the library database's metadata, read-only, into a folder to bring back. Windows authentication.
#   powershell -ExecutionPolicy Bypass -File collect_metadata.ps1 -Server . -Database Db2BDoctorNew
param([string]$Server = ".", [string]$Database = "Db2BDoctorNew")
$ErrorActionPreference = "Stop"
$out = Join-Path $PSScriptRoot ("metadata_" + (Get-Date -Format "yyyyMMdd_HHmmss"))
New-Item -ItemType Directory -Path $out | Out-Null
$sql = Join-Path $PSScriptRoot "collect_metadata.sql"
sqlcmd -E -S $Server -d $Database -i $sql -o (Join-Path $out "metadata.txt") -W -w 4000 -s "|"
# the same, as one CSV per lookup table, easier to read back
$tables = "TblOperationInfo","TblOperationTypeInfo","TblStatusRefInfo","TblPaymentTypeInfo","TblSalesTypeInfo","TblRowStatusInfo","TblBranchInfo","TblStoreInfo","TblCashDeskInfo","TblCurrentDate","TblAdjustmentResonInfo"
foreach ($t in $tables) { sqlcmd -E -S $Server -d $Database -Q "SET NOCOUNT ON; SELECT * FROM dbo.$t" -o (Join-Path $out "$t.csv") -W -w 4000 -s "," }
sqlcmd -E -S $Server -d $Database -Q "SET NOCOUNT ON; SELECT TABLE_NAME, COLUMN_NAME, DATA_TYPE, IS_NULLABLE, COLUMNPROPERTY(OBJECT_ID('dbo.'+TABLE_NAME), COLUMN_NAME, 'IsIdentity') AS is_identity FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='dbo' ORDER BY TABLE_NAME, ORDINAL_POSITION" -o (Join-Path $out "columns.csv") -W -w 4000 -s ","
Write-Host "Written to $out. Zip the folder and bring it back; nothing on the server was changed."
