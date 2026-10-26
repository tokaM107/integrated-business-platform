# IMED ERP - library metadata collector (read-only). Double-click COLLECT_METADATA.bat; it runs this script.
#
# What it does, on the library's Windows PC, with the Windows login of the person running it:
#   1. finds the SQL Server instance and the database (Db2BDoctorNew, or the one named below)
#   2. reads, with SELECT statements only: the tables and their columns, keys and indexes, the row counts, the
#      lookup tables (operation / status / payment / sales types, branches, stores, cash desks), the text of
#      every procedure, view and function, counts of documents per operation and status, and a few sample
#      documents with personal data masked
#   3. writes a REPORT.txt that says PASS or FAIL for each step, and zips everything into ONE file on the Desktop:
#      library_metadata_<date>.zip
# Nothing is written to the database. No password is asked or stored. Phones, addresses, e-mails, passwords,
# card/insurance/national numbers, IPs, file paths and customer/vendor/user names are masked or left out.
#
# Works on Windows PowerShell 5.1 (every Windows 10/11) with .NET's own SqlClient; needs no sqlcmd, no module.
#   -Database  the database name (default Db2BDoctorNew)
#   -Server    skip the search and use this server, e.g. ".\SQLEXPRESS"
#   -MockFile  for tests only: a JSON file with canned answers instead of a database
param(
	[string]$Database = "Db2BDoctorNew",
	[string]$Server = "",
	[string]$OutRoot = "",
	[string]$MockFile = ""
)
$ErrorActionPreference = "Stop"
$script:Checks = New-Object System.Collections.ArrayList
$script:Conn = $null
$script:Mock = $null
$stamp = Get-Date -Format "yyyyMMdd_HHmm"
if (-not $OutRoot) { $OutRoot = if ($MockFile) { Join-Path ([System.IO.Path]::GetTempPath()) "library_metadata_test" } else { [Environment]::GetFolderPath("Desktop") } }
$Out = Join-Path $OutRoot ("library_metadata_" + $stamp)
New-Item -ItemType Directory -Force -Path $Out | Out-Null
foreach ($d in "lookups", "samples", "code") { New-Item -ItemType Directory -Force -Path (Join-Path $Out $d) | Out-Null }
$Log = Join-Path $Out "collector_log.txt"

function Say($text) { $line = "[" + (Get-Date -Format "HH:mm:ss") + "] " + $text; Write-Host $line; Add-Content -Path $Log -Value $line -Encoding UTF8 }
function Check($name, $ok, $detail) { [void]$script:Checks.Add([pscustomobject]@{ step = $name; result = $(if ($ok) { "PASS" } else { "FAIL" }); detail = $detail }); Say ("{0,-4} {1}: {2}" -f $(if ($ok) { "PASS" } else { "FAIL" }), $name, $detail) }

# ---------- column-name rules: what is masked, what is left out ----------
$SensitivePattern = '(?i)(phone|mobile|tel\b|mail|address|password|passw|pwd|pass\b|national|card|insuran|birth|salary|\bip\b|txtbranchip|path|serial|website|web\b|contact|remarks|notes)'
$NamePattern = '(?i)(customer|vendor|vendore|employee|user|salesman|person)(full)?name'
$SkipRowsTables = @("TblUserInfo", "TblAppSetupInfo", "TblCustomerInfo", "TblEmployeeInfo", "TblVendorInfo", "TblUserLogs", "TblSendMailLog", "TblCallerId", "TblReplicationBasicData", "TblBankAccInfo", "TblBankInfo")

function Mask-Value($column, $value) {
	if ($null -eq $value -or $value -is [System.DBNull]) { return $value }
	if ($column -match $SensitivePattern) { return "[redacted]" }
	if ($column -match $NamePattern) {
		$sha = [System.Security.Cryptography.SHA1]::Create()
		$hash = [BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes([string]$value))).Replace("-", "").Substring(0, 8)
		return "name#" + $hash
	}
	return $value
}

# ---------- the database (or the mock) ----------
function Open-Db {
	if ($MockFile) { $script:Mock = Get-Content -Raw -Path $MockFile -Encoding UTF8 | ConvertFrom-Json; Say "MOCK MODE: reading $MockFile, no database is touched"; return "mock" }
	$candidates = @()
	if ($Server) { $candidates += $Server }
	else {
		$candidates += ".", "localhost", "(local)"
		try {
			$key = "HKLM:\SOFTWARE\Microsoft\Microsoft SQL Server\Instance Names\SQL"
			if (Test-Path $key) { (Get-Item $key).Property | ForEach-Object { if ($_ -ne "MSSQLSERVER") { $candidates += ".\$_"; $candidates += "localhost\$_" } } }
		} catch { }
		$candidates += ".\SQLEXPRESS", "localhost\SQLEXPRESS"
	}
	foreach ($c in ($candidates | Select-Object -Unique)) {
		try {
			$cs = "Server=$c;Database=master;Integrated Security=True;Connect Timeout=6;ApplicationIntent=ReadOnly"
			$conn = New-Object System.Data.SqlClient.SqlConnection $cs
			$conn.Open()
			$cmd = $conn.CreateCommand(); $cmd.CommandText = "SELECT name FROM sys.databases ORDER BY name"
			$dbs = @(); $r = $cmd.ExecuteReader(); while ($r.Read()) { $dbs += $r.GetString(0) }; $r.Close(); $conn.Close()
			Say "SQL Server found at '$c'; databases: $($dbs -join ', ')"
			if ($dbs -notcontains $Database) {
				$guess = $dbs | Where-Object { $_ -match '(?i)doctor|market|tanmya' } | Select-Object -First 1
				if ($guess) { Say "Database '$Database' not found; using '$guess' instead"; $script:Database = $guess }
				else { throw "Database '$Database' is not on server '$c'. Databases there: $($dbs -join ', ')" }
			}
			$cs = "Server=$c;Database=$($script:Database);Integrated Security=True;Connect Timeout=10;ApplicationIntent=ReadOnly"
			$script:Conn = New-Object System.Data.SqlClient.SqlConnection $cs
			$script:Conn.Open()
			$cmd = $script:Conn.CreateCommand(); $cmd.CommandText = "SET TRANSACTION ISOLATION LEVEL READ COMMITTED"; [void]$cmd.ExecuteNonQuery()
			return $c
		} catch { Say "no server at '$c' ($($_.Exception.Message.Split([char]10)[0]))" }
	}
	throw "No SQL Server answered. Open 'SQL Server Configuration Manager' or 'Services' and check that the SQL Server service is running, then run again; or run with -Server '<name>'."
}

# Rows of one SELECT, as objects. $Name is the step name (the mock answers by it). SELECT only, by construction.
function Get-Rows($Name, $Sql, $Params) {
	if ($script:Mock) { $rows = $script:Mock.$Name; if ($null -eq $rows) { return @() }; return @($rows) }
	if ($Sql -notmatch '^\s*(SELECT|WITH)\b') { throw "refusing a statement that is not a SELECT: $Sql" }
	$cmd = $script:Conn.CreateCommand(); $cmd.CommandText = $Sql; $cmd.CommandTimeout = 300
	if ($Params) { foreach ($k in $Params.Keys) { [void]$cmd.Parameters.AddWithValue($k, $Params[$k]) } }
	$table = New-Object System.Data.DataTable
	$adapter = New-Object System.Data.SqlClient.SqlDataAdapter $cmd
	[void]$adapter.Fill($table)
	$rows = @()
	foreach ($row in $table.Rows) { $o = [ordered]@{}; foreach ($col in $table.Columns) { $o[$col.ColumnName] = $row[$col] }; $rows += [pscustomobject]$o }
	return $rows
}

function Save-Csv($rows, $file) { if ($rows.Count -gt 0) { $rows | Export-Csv -Path $file -NoTypeInformation -Encoding UTF8 } else { Set-Content -Path $file -Value "" -Encoding UTF8 } }
function Masked($rows) { foreach ($r in $rows) { $o = [ordered]@{}; foreach ($p in $r.PSObject.Properties) { $o[$p.Name] = Mask-Value $p.Name $p.Value }; [pscustomobject]$o } }

# ---------- the steps ----------
function Step($name, $work) { try { & $work } catch { Check $name $false ("ERROR: " + $_.Exception.Message.Split([char]10)[0]) } }

Say "IMED ERP library metadata collector. Output folder: $Out"
$server = $null
Step "connect" { $script:server = Open-Db; Check "connect" $true "server '$($script:server)', database '$($script:Database)', Windows login of the current user" }
if (-not $script:server) { Check "connect" $false "no connection; nothing else can run"; }
else {
	Step "server" {
		$rows = Get-Rows "server" "SELECT @@VERSION AS version, DB_NAME() AS db, CONVERT(sysname, DATABASEPROPERTYEX(DB_NAME(), 'Collation')) AS collation, GETDATE() AS now_local, SUSER_SNAME() AS login_name, HAS_PERMS_BY_NAME(DB_NAME(), 'DATABASE', 'SELECT') AS can_select"
		$rows | ConvertTo-Json -Depth 3 | Set-Content -Path (Join-Path $Out "server.json") -Encoding UTF8
		Check "server" ($rows.Count -eq 1) ("version " + ([string]$rows[0].version).Split([char]10)[0])
	}
	$columns = @()
	Step "columns" {
		$script:columns = Get-Rows "columns" "SELECT c.TABLE_NAME, c.ORDINAL_POSITION, c.COLUMN_NAME, c.DATA_TYPE, c.CHARACTER_MAXIMUM_LENGTH, c.NUMERIC_PRECISION, c.NUMERIC_SCALE, c.IS_NULLABLE, c.COLUMN_DEFAULT, COLUMNPROPERTY(OBJECT_ID(c.TABLE_SCHEMA + '.' + c.TABLE_NAME), c.COLUMN_NAME, 'IsIdentity') AS is_identity, COLUMNPROPERTY(OBJECT_ID(c.TABLE_SCHEMA + '.' + c.TABLE_NAME), c.COLUMN_NAME, 'IsComputed') AS is_computed FROM INFORMATION_SCHEMA.COLUMNS c JOIN INFORMATION_SCHEMA.TABLES t ON t.TABLE_SCHEMA = c.TABLE_SCHEMA AND t.TABLE_NAME = c.TABLE_NAME WHERE c.TABLE_SCHEMA = 'dbo' AND t.TABLE_TYPE = 'BASE TABLE' ORDER BY c.TABLE_NAME, c.ORDINAL_POSITION"
		Save-Csv $script:columns (Join-Path $Out "columns.csv")
		$tables = @($script:columns | Select-Object -ExpandProperty TABLE_NAME -Unique)
		$needed = @("TblRefStockHead", "TblRefStockSub", "TblRefCashReceiptHead", "TblRefCashReceiptSub", "TblRefCashPaymentHead", "TblRefCashPaymentSub", "TblOperationInfo", "TblStatusRefInfo", "TblCustomerInfo", "TblProductInfo", "TblDoctorInfo", "TblBranchInfo")
		$missing = @($needed | Where-Object { $tables -notcontains $_ })
		Check "columns" ($tables.Count -ge 60 -and $missing.Count -eq 0) ("$($tables.Count) tables, $($script:columns.Count) columns" + $(if ($missing.Count) { "; MISSING: $($missing -join ', ')" } else { "" }))
	}
	Step "keys" {
		$k = Get-Rows "keys" "SELECT kc.name AS constraint_name, kc.type_desc, t.name AS table_name, c.name AS column_name, ic.key_ordinal FROM sys.key_constraints kc JOIN sys.tables t ON t.object_id = kc.parent_object_id JOIN sys.index_columns ic ON ic.object_id = t.object_id AND ic.index_id = kc.unique_index_id JOIN sys.columns c ON c.object_id = t.object_id AND c.column_id = ic.column_id ORDER BY t.name, kc.name, ic.key_ordinal"
		Save-Csv $k (Join-Path $Out "keys.csv")
		$fk = Get-Rows "foreign_keys" "SELECT fk.name, tp.name AS parent_table, cp.name AS parent_column, tr.name AS ref_table, cr.name AS ref_column FROM sys.foreign_keys fk JOIN sys.foreign_key_columns fkc ON fkc.constraint_object_id = fk.object_id JOIN sys.tables tp ON tp.object_id = fkc.parent_object_id JOIN sys.columns cp ON cp.object_id = tp.object_id AND cp.column_id = fkc.parent_column_id JOIN sys.tables tr ON tr.object_id = fkc.referenced_object_id JOIN sys.columns cr ON cr.object_id = tr.object_id AND cr.column_id = fkc.referenced_column_id ORDER BY tp.name"
		Save-Csv $fk (Join-Path $Out "foreign_keys.csv")
		$ix = Get-Rows "indexes" "SELECT t.name AS table_name, i.name AS index_name, i.type_desc, i.is_unique, i.is_primary_key, c.name AS column_name, ic.key_ordinal FROM sys.indexes i JOIN sys.tables t ON t.object_id = i.object_id JOIN sys.index_columns ic ON ic.object_id = i.object_id AND ic.index_id = i.index_id JOIN sys.columns c ON c.object_id = t.object_id AND c.column_id = ic.column_id WHERE i.name IS NOT NULL ORDER BY t.name, i.name, ic.key_ordinal"
		Save-Csv $ix (Join-Path $Out "indexes.csv")
		Check "keys" $true "$($k.Count) key columns, $($fk.Count) foreign keys, $($ix.Count) index columns"
	}
	Step "objects" {
		$o = Get-Rows "objects" "SELECT o.name, o.type_desc, o.create_date, o.modify_date FROM sys.objects o WHERE o.schema_id = SCHEMA_ID('dbo') AND o.type IN ('U','V','P','FN','IF','TF') ORDER BY o.type_desc, o.name"
		Save-Csv $o (Join-Path $Out "objects.csv")
		Check "objects" ($o.Count -ge 1000) "$($o.Count) objects (the Generate-Scripts report listed 1,740)"
	}
	Step "counts" {
		$c = Get-Rows "counts" "SELECT t.name AS table_name, SUM(p.rows) AS row_count FROM sys.tables t JOIN sys.partitions p ON p.object_id = t.object_id AND p.index_id IN (0, 1) WHERE t.schema_id = SCHEMA_ID('dbo') GROUP BY t.name ORDER BY t.name"
		Save-Csv $c (Join-Path $Out "row_counts.csv")
		$heads = $c | Where-Object { $_.table_name -eq "TblRefStockHead" } | Select-Object -First 1
		Check "counts" ($c.Count -ge 60) ("$($c.Count) tables counted; TblRefStockHead has " + $(if ($heads) { "$($heads.row_count)" } else { "?" }) + " documents")
	}
	Step "lookups" {
		$lookups = @("TblOperationInfo", "TblOperationTypeInfo", "TblStatusRefInfo", "TblPaymentTypeInfo", "TblSalesTypeInfo", "TblRowStatusInfo", "TblAdjustmentResonInfo", "TblAdjustmentResonTypeInfo", "TblBranchInfo", "TblStoreInfo", "TblCashDeskInfo", "TblCasherTypeInfo", "TblDrawerTypeInfo", "TblCurrentDate", "TblDoctorInfo", "TblProductCategoryInfo", "TblProductGroupInfo", "TblProductUnitInfo", "TblPriceListInfo", "TblSalesTypeInfo", "TblLogStatusInfo", "TblStatusRefInfo", "TblFormReportInfo", "TblGSupportInfo", "TblAreaInfo") | Select-Object -Unique
		$done = 0; $empty = @(); $found = @{}
		foreach ($t in $lookups) {
			$cols = @($script:columns | Where-Object { $_.TABLE_NAME -eq $t })
			if ($cols.Count -eq 0) { continue }
			# balances and begin dates are the library's figures, not needed for the mapping: left out of the lookups
			$keep = @($cols | Where-Object { $_.COLUMN_NAME -notmatch $SensitivePattern -and $_.COLUMN_NAME -notmatch '(?i)balance|begindate|value' } | ForEach-Object { "[" + $_.COLUMN_NAME + "]" })
			if ($keep.Count -eq 0) { continue }
			$rows = Get-Rows "lookup:$t" ("SELECT TOP 5000 " + ($keep -join ", ") + " FROM dbo.[" + $t + "]")
			$names = @($keep | ForEach-Object { $_.Trim("[", "]") })
			$rows = @($rows | ForEach-Object { $o = [ordered]@{}; foreach ($n in $names) { $o[$n] = $_.$n }; [pscustomobject]$o })
			Save-Csv (Masked $rows) (Join-Path (Join-Path $Out "lookups") ($t + ".csv"))
			$done++; $found[$t] = $rows.Count; if ($rows.Count -eq 0) { $empty += $t }
		}
		$opN = [int]$found["TblOperationInfo"]; $stN = [int]$found["TblStatusRefInfo"]
		Check "lookups" ($done -ge 10 -and $opN -gt 0 -and $stN -gt 0) ("$done lookup tables written; operations: $opN rows, statuses: $stN rows" + $(if ($empty.Count) { "; empty: $($empty -join ', ')" } else { "" }))
	}
	Step "code" {
		$m = Get-Rows "code" "SELECT o.name, o.type_desc, m.definition FROM sys.sql_modules m JOIN sys.objects o ON o.object_id = m.object_id WHERE o.schema_id = SCHEMA_ID('dbo') ORDER BY o.type_desc, o.name"
		$sb = New-Object System.Text.StringBuilder
		foreach ($r in $m) {
			$text = ([string]$r.definition) -replace "(?i)(password|pwd)\s*=\s*'[^']*'", "`$1='[redacted]'"
			[void]$sb.AppendLine("-- ===== " + $r.type_desc + " " + $r.name + " =====")
			[void]$sb.AppendLine($text)
			[void]$sb.AppendLine("GO")
		}
		Set-Content -Path (Join-Path (Join-Path $Out "code") "all_modules.sql") -Value $sb.ToString() -Encoding UTF8
		$m | Select-Object name, type_desc | Export-Csv -Path (Join-Path (Join-Path $Out "code") "index.csv") -NoTypeInformation -Encoding UTF8
		$key = @("SPrFSSSInsert", "SPrFSSSBtnIssueUpdate", "SPrFSSSFillDGVSalesSmallStockSub", "SPrFSSSIOAddToLedgerMovementDoctor", "SPrFCashRInsert", "SPrRptSalesSmallStockCashCasher", "SPrFRDSSumAllSales")
		$have = @($m | Where-Object { $key -contains $_.name }).Count
		Check "code" ($m.Count -ge 1000 -and $have -ge 5) "$($m.Count) definitions saved; $have of $($key.Count) key procedures present"
	}
	Step "documents" {
		$results = @()
		foreach ($t in "TblRefStockHead", "TblRefCashReceiptHead", "TblRefCashPaymentHead", "TblRefJournalEntryHead") {
			$cols = @($script:columns | Where-Object { $_.TABLE_NAME -eq $t } | Select-Object -ExpandProperty COLUMN_NAME)
			if ($cols.Count -eq 0) { continue }
			$op = $cols | Where-Object { $_ -match '(?i)operationcode' } | Select-Object -First 1
			$st = $cols | Where-Object { $_ -match '(?i)statuscode' } | Select-Object -First 1
			$dt = $cols | Where-Object { $_ -match '(?i)regdate|date' } | Select-Object -First 1
			$id = ($script:columns | Where-Object { $_.TABLE_NAME -eq $t -and [string]$_.is_identity -eq "1" } | Select-Object -First 1 -ExpandProperty COLUMN_NAME)
			if (-not $id) { $id = $cols | Where-Object { $_ -match '(?i)^txtid' } | Select-Object -First 1 }
			$group = @(); if ($op) { $group += "[$op]" }; if ($st) { $group += "[$st]" }
			$sel = ($group + @("COUNT(*) AS n") + $(if ($dt) { @("MIN([$dt]) AS first_date", "MAX([$dt]) AS last_date") } else { @() }) + $(if ($id) { @("MAX([$id]) AS max_id", "MIN([$id]) AS min_id") } else { @() })) -join ", "
			$sql = "SELECT '$t' AS table_name, " + $sel + " FROM dbo.[$t]" + $(if ($group.Count) { " GROUP BY " + ($group -join ", ") + " ORDER BY " + ($group -join ", ") } else { "" })
			$rows = Get-Rows "documents:$t" $sql
			$results += $rows
			Save-Csv $rows (Join-Path $Out ("documents_by_code_" + $t + ".csv"))
		}
		Check "documents" ($results.Count -gt 0) "$($results.Count) (table, operation, status) groups counted"
	}
	Step "samples" {
		$n = 0
		foreach ($pair in @(@("TblRefStockHead", "TblRefStockSub", 30, 200), @("TblRefCashReceiptHead", "TblRefCashReceiptSub", 10, 50), @("TblRefCashPaymentHead", "TblRefCashPaymentSub", 10, 50))) {
			$head, $sub, $nh, $ns = $pair
			$hcols = @($script:columns | Where-Object { $_.TABLE_NAME -eq $head } | Select-Object -ExpandProperty COLUMN_NAME)
			if ($hcols.Count -eq 0) { continue }
			$id = ($script:columns | Where-Object { $_.TABLE_NAME -eq $head -and [string]$_.is_identity -eq "1" } | Select-Object -First 1 -ExpandProperty COLUMN_NAME)
			if (-not $id) { $id = $hcols | Where-Object { $_ -match '(?i)^txtid' } | Select-Object -First 1 }
			if (-not $id) { $id = $hcols[0] }
			$heads = Get-Rows "sample:$head" "SELECT TOP $nh * FROM dbo.[$head] ORDER BY [$id] DESC"
			Save-Csv (Masked $heads) (Join-Path (Join-Path $Out "samples") ($head + ".csv"))
			$scols = @($script:columns | Where-Object { $_.TABLE_NAME -eq $sub } | Select-Object -ExpandProperty COLUMN_NAME)
			$link = $scols | Where-Object { $_ -eq $id } | Select-Object -First 1
			if (-not $link) { $link = $scols | Where-Object { $_ -match ('(?i)' + [regex]::Escape($id)) } | Select-Object -First 1 }
			if ($link -and $heads.Count -gt 0) {
				$ids = ($heads | ForEach-Object { [string]$_.$id } | Where-Object { $_ -match '^\d+$' }) -join ","
				if ($ids) { $lines = Get-Rows "sample:$sub" "SELECT TOP $ns * FROM dbo.[$sub] WHERE [$link] IN ($ids) ORDER BY [$link] DESC"; Save-Csv (Masked $lines) (Join-Path (Join-Path $Out "samples") ($sub + ".csv")); $n += $lines.Count }
			}
			$n += $heads.Count
		}
		Check "samples" ($n -gt 0) "$n sample rows written, names and personal data masked"
	}
	if ($script:Conn) { $script:Conn.Close() }
}

# ---------- the report and the zip ----------
$fails = @($script:Checks | Where-Object { $_.result -eq "FAIL" })
$verdict = if ($fails.Count -eq 0) { "SUCCESS: collection complete. Bring back the ZIP named below." } else { "FAILURE: $($fails.Count) step(s) failed. Bring back the ZIP anyway (it holds the log); the failed steps are listed below." }
$report = @("IMED ERP - library metadata collection", "Date: $(Get-Date -Format 'yyyy-MM-dd HH:mm')", "Database: $Database", "", $verdict, "") + ($script:Checks | ForEach-Object { "{0,-4} {1,-10} {2}" -f $_.result, $_.step, $_.detail }) + @("", "Nothing was written to the database. Personal data was masked (see collector_log.txt).")
Set-Content -Path (Join-Path $Out "REPORT.txt") -Value ($report -join [Environment]::NewLine) -Encoding UTF8
$zip = Join-Path $OutRoot ("library_metadata_" + $stamp + ".zip")
if (Test-Path $zip) { Remove-Item $zip -Force }
Compress-Archive -Path $Out -DestinationPath $zip -Force
Write-Host ""
Write-Host "=================================================================="
Write-Host $verdict
Write-Host "ZIP file to bring back:  $zip"
Write-Host "=================================================================="
$report | Select-Object -Skip 5 | ForEach-Object { Write-Host $_ }
if ($fails.Count -gt 0) { exit 1 } else { exit 0 }
