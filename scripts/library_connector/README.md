# Library connector (Tanmya Market, SQL Server → IMED ERP)

Runs on the library's Windows PC, reads the library system's database read-only and pushes issued documents to
the ERP. Design and findings: `docs/LIBRARY_SQLSERVER_INTEGRATION_ANALYSIS.md`.

1. **Next on-site session (read-only):** `powershell -ExecutionPolicy Bypass -File collect_metadata.ps1` and bring
   back the `metadata_<date>` folder. It needs `sqlcmd` (SQL Server command line utilities) and your Windows login.
2. **Then, remotely:** fill `config.json` from `config.example.json` with the confirmed column names, the operation
   and status codes (`TblOperationInfo`, `TblStatusRefInfo`), the branch → cost center map, and the ERP user's
   API key and secret (a user with the Accounts Manager role, made for the connector).
3. **Dry run on the PC:** `python tanmya_connector.py --dry-run` writes `batch_<date>.json` and posts nothing.
   Check it, then `python tanmya_connector.py` for the first real batch and schedule the same command every
   10 minutes with Task Scheduler. Needs Python 3.9+, `pip install pyodbc requests`, and the Microsoft ODBC
   Driver 17 or 18 for SQL Server.

The ERP keys every document on its source id, skips an unchanged one and updates a changed one, so running the
connector twice is harmless. The ERP posts nothing from these documents: they are a read-only mirror.
