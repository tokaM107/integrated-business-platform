# Library connector (Tanmya Market, SQL Server → IMED ERP)

Design and findings: `docs/LIBRARY_SQLSERVER_INTEGRATION_ANALYSIS.md`. Everything here is read-only toward the
library's database.

| File | Purpose |
|---|---|
| `COLLECT_METADATA.bat` + `collect_metadata.ps1` | **The one-click metadata collector** for the next visit: double-click the `.bat` on the library PC, bring back the ZIP it leaves on the Desktop. Plain instructions, English and Arabic: `INSTRUCTIONS.md`. Needs nothing installed (Windows PowerShell 5.1 and .NET's SqlClient are part of Windows); uses the Windows login; masks personal data; writes `REPORT.txt` with PASS/FAIL per step. |
| `tests/mock_db.json`, `tests/mock_db_failing.json` | Canned database answers to run the collector without SQL Server: `pwsh -File collect_metadata.ps1 -MockFile tests/mock_db.json -OutRoot /tmp/x` (tested in the `mcr.microsoft.com/powershell` container on 26 Oct 2026; the failing fixture must end in FAILURE and exit code 1). |
| `tanmya_connector.py` + `config.example.json` | The connector that will run on the library PC every 10 minutes once the metadata is known: SELECT only, incremental, posts to the ERP (`imed_erp.imederp.library_sync.sync.receive`) with token auth; `--dry-run` writes the batch to a file. Needs Python 3.9+, `pyodbc`, `requests`, the Microsoft ODBC Driver 17/18. |

| `config.pc1.example.json` | The template for **PC1** (database `Db2BDoctor`, library name `pc1`). |
| `install_task.ps1` | Registers the connector in Task Scheduler every 10 minutes as the library's Windows user; refuses while `--check` fails. |

Order of work: collect the metadata (on site, one click) → fill `config.json` from the ZIP (remote) → `--check` →
`--dry-run` on the PC → first real batch → `install_task.ps1`.

## Two libraries, two PCs (27 Oct 2026)

The first library's PC holds `Db2BDoctorNew`; **PC1** holds `Db2BDoctor`. Both are the same Tanmya application
and both number their documents from 1, so each PC's `config.json` names its library (`"library": "pc1"`, and a
name for the first, e.g. `"azarita"`), the connector sends it with every batch, and the ERP keys every mirrored
document on it: `tanmya:pc1:stock:90001` and `tanmya:azarita:stock:90001` are two documents. The ERP refuses a
batch without a library name. Both PCs post as the same ERP user, `library-connector@imed.local` (role *Library
Connector* only; `imed_erp.setup.setup_library_connector.run`), whose API key and secret are generated on the
user's form and typed into each `config.json`. The schema in hand is Db2BDoctorNew's; PC1's collector run
confirms Db2BDoctor's before its first import. The whole procedure: docs/PRODUCTION_DEPLOYMENT_COOLIFY.md, section 8.
