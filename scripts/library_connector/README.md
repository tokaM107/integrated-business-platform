# Library connector (Tanmya Market, SQL Server → IMED ERP)

Design and findings: `docs/LIBRARY_SQLSERVER_INTEGRATION_ANALYSIS.md`. Everything here is read-only toward the
library's database.

| File | Purpose |
|---|---|
| `COLLECT_METADATA.bat` + `collect_metadata.ps1` | **The one-click metadata collector** for the next visit: double-click the `.bat` on the library PC, bring back the ZIP it leaves on the Desktop. Plain instructions, English and Arabic: `INSTRUCTIONS.md`. Needs nothing installed (Windows PowerShell 5.1 and .NET's SqlClient are part of Windows); uses the Windows login; masks personal data; writes `REPORT.txt` with PASS/FAIL per step. |
| `tests/mock_db.json`, `tests/mock_db_failing.json` | Canned database answers to run the collector without SQL Server: `pwsh -File collect_metadata.ps1 -MockFile tests/mock_db.json -OutRoot /tmp/x` (tested in the `mcr.microsoft.com/powershell` container on 26 Oct 2026; the failing fixture must end in FAILURE and exit code 1). |
| `tanmya_connector.py` + `config.example.json` | The connector that will run on the library PC every 10 minutes once the metadata is known: SELECT only, incremental, posts to the ERP (`imed_erp.imederp.library_sync.sync.receive`) with token auth; `--dry-run` writes the batch to a file. Needs Python 3.9+, `pyodbc`, `requests`, the Microsoft ODBC Driver 17/18. |

Order of work: collect the metadata (on site, one click) → fill `config.json` from the ZIP (remote) → dry run on
the PC → first real batch → Task Scheduler every 10 minutes.
