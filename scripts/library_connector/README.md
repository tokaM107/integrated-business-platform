# Library connector (Tanmya Market, SQL Server → IMED ERP)

Design and findings: `docs/integrations/library/sqlserver-integration-analysis.md`. Everything here is read-only toward the
library's database.

| File | Purpose |
|---|---|
| `COLLECT_METADATA.bat` + `collect_metadata.ps1` | **The one-click metadata collector** for the next visit: double-click the `.bat` on the library PC, bring back the ZIP it leaves on the Desktop. Plain instructions, English and Arabic: `INSTRUCTIONS.md`. Needs nothing installed (Windows PowerShell 5.1 and .NET's SqlClient are part of Windows); uses the Windows login; masks personal data; writes `REPORT.txt` with PASS/FAIL per step. |
| `tests/mock_db.json`, `tests/mock_db_failing.json` | Canned database answers to run the collector without SQL Server: `pwsh -File collect_metadata.ps1 -MockFile tests/mock_db.json -OutRoot /tmp/x` (tested in the `mcr.microsoft.com/powershell` container on 26 Oct 2026; the failing fixture must end in FAILURE and exit code 1). |
| `tanmya_connector.py` + `config.example.json` | The connector that will run on the library PC every 10 minutes once the metadata is known: SELECT only, incremental, posts to the ERP (`imed_erp.imederp.library_sync.sync.receive`) with token auth; `--dry-run` writes the batch to a file. Needs Python 3.9+, `pyodbc`, `requests`, the Microsoft ODBC Driver 17/18. |

| `config.pc1.example.json` | **PC1's config, filled from its metadata ZIP of 3 Nov 2026** (the Azarita library, branch 10, SQL Server 2008 R2, database `Db2BDoctor`): the real columns, the operation codes, issued 11 / cancelled 13, the ERP URL. Only the API key and secret stay placeholders. |
| `SETUP_CONNECTOR.bat` | Double-click on the PC: finds Python (where python.org installs it, whatever the PATH), checks the ODBC driver, installs `pyodbc` and `requests`, `--check`, then a `--dry-run`. |
| `SET_KEYS.bat` + `set_keys.ps1` | Double-click: asks for the connector user's API key and secret and writes them into `config.json` (no hand-editing of JSON). |
| `UPDATE_CONFIG.bat` + `update_config.ps1` | Double-click on a PC already running: brings its `config.json` up to date (4 Nov 2026: the stock query also reads `TxtOrderTime`, the time the cashier saved the invoice) and keeps its API key and secret; the old file stays as `config.json.bak`; running it twice changes nothing. |
| `MAKE_SAMPLE.bat` + `make_sample.py` | Cuts `sample.json` (3 sales, a return, a cancelled document) out of the newest dry run, small enough to copy off the PC and post as a first test with `--from-json`. |
| `INSTALL_TASK.bat` + `install_task.ps1` | Runs the connector every 10 minutes, hidden, as the library's Windows user: a Task Scheduler task, or the Startup folder when Task Scheduler is denied; refuses while `--check` fails. |
| `START_CONNECTOR.bat` | For a PC whose antivirus denies both (PC1, 3 Nov 2026): a window that runs the connector now and every 10 minutes while it stays open. Someone double-clicks it after each start of the PC. |

Order of work: collect the metadata (on site, one click) → fill `config.json` from the ZIP (remote) → `SETUP_CONNECTOR`
(`--check`, `--dry-run`) → `SET_KEYS` → a first small batch → `INSTALL_TASK` (or `START_CONNECTOR`).

PC1 went live on 3 Nov 2026: 53,662 documents in the dry run (retail sales 18 and returns 19 only), every issued
sale's lines equal to its cash + visa + credit; 53,674 mirrored by the end of the first run. Task Scheduler and the
Startup folder are denied on PC1 (an antivirus, even as administrator), so it runs through `START_CONNECTOR.bat`
until the folder is excluded in the antivirus.

## Two libraries, two PCs (27 Oct 2026)

The first library's PC holds `Db2BDoctorNew`; **PC1** holds `Db2BDoctor`. Both are the same Tanmya application
and both number their documents from 1, so each PC's `config.json` names its library (`"library": "pc1"`, and a
name for the first, e.g. `"azarita"`), the connector sends it with every batch, and the ERP keys every mirrored
document on it: `tanmya:pc1:stock:90001` and `tanmya:azarita:stock:90001` are two documents. The ERP refuses a
batch without a library name. Both PCs post as the same ERP user, `library-connector@imed.local` (role *Library
Connector* only; `imed_erp.setup.setup_library_connector.run`), whose API key and secret are generated on the
user's form and typed into each `config.json`. The schema in hand is Db2BDoctorNew's; PC1's collector run
confirms Db2BDoctor's before its first import. The whole procedure: docs/deployment/production-deployment-coolify.md, section 8.
