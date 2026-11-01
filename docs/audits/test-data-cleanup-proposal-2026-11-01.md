# ERPNext test data on the production site: inventory and cleanup proposal (1 Nov 2026)

Found by read-only queries on 1 Nov 2026. None of it reaches the group's figures today: every dashboard figure,
report and chart filters on the company `Mohamed Mamdouh group` (the stock chart since ae2162c). The risk is a user
picking a `_Test` record in a form, and clutter in lists.

## Inventory

| Kind | Records | References from real data | Class |
|---|---|---|---|
| Companies | 21 (`_Test Company`…`_Test Company 7`, Wind Power LLC, Parent/Child Company India/US, Best Test, UAE/SA VAT, Opening Invoice, Trial Balance, Support SLA, Quality, PCV) with ~1,900 accounts, cost centers, warehouses | none from MMG documents | clearly unused |
| Stock | 2 Stock Entries, 2 Stock Ledger Entries, 3 Bins (value 2,000) in `_Test Warehouse - _TC` | none | clearly unused, but **posted documents**: cancel before deleting the company |
| Items | 20 `_Test …` items; 3 non-test items on `_Test UOM` (`Loyal Item`, `Photocopier`, `138-CMS Shoe`, ERPNext demo items) | 0 sales lines | clearly unused |
| Item groups, customer groups, territories, UOMs | 13 / 2 / 5 / 2 `_Test …` | 12 customers sit in `_Test Customer Group` (all `_Test`/demo customers, none with an XStudio id) | unused |
| Customers, suppliers | 10 / 10 `_Test …` + demo (Prestiga-Biz, Test Loyalty Customer) | none | unused |
| Fiscal years | 50+ `_Test Fiscal Year 20xx`; the real ones are 2026-2027 and 2027-2028 (MMG is also listed on 2027-2028 next to the test companies, which is fine) | — | unused; removing them does not touch the real two |
| Users | 9 `test…@example.com` | — | disable, not delete (audit trail) |

Potentially referenced by real configuration: none found (POS profiles, price lists, XStudio customer group, printing
machines, warehouses of MMG all point to MMG records). Unsafe to remove: nothing, provided the order below.

## Proposal (not executed)

1. Backup first (the nightly one plus `bench backup --with-files`).
2. Cancel and delete the 2 test Stock Entries (this clears the SLEs and Bins).
3. Delete the 21 test companies with ERPNext's own "Delete Company Transactions", then the companies (their
   accounts, cost centers, warehouses go with them).
4. Delete `_Test` items, item groups, customer groups, territories, UOMs, customers, suppliers, fiscal years,
   in that order, each by name list from `imed_erp.setup.list_test_records.run` (read-only listing).
5. Disable the test users.
6. Run the test-record guard and the full suite's `test_test_records` afterwards; verify counts on the dashboard.

Rollback: the backup of step 1 (`deploy/restore_site.sh` with `FORCE=1`). Expected effect on real data: none; the
Owner Dashboard's figures are unchanged because they never included these records.
