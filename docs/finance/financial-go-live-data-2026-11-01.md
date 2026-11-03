# Financial go-live: the data the owner and the accountant must supply (1 Nov 2026)

Production holds no accounting record yet (0 GL entries, invoices, payments, stock entries). Nothing below is
posted by the system on its own: every opening is a **draft** that the accountant reviews and submits.

## 1. Opening cash and wallet balances

Sheet: `apps/imed_erp/imed_erp/setup/data/opening_cash_template.csv` (one row per account, prefilled).

| Account | Kind | Business that closes it | Who counts | Who approves | Evidence |
|---|---|---|---|---|---|
| خزينة مكتبة الأزاريطة | cash box | مكتبة الأزاريطة (Sara) | branch manager | accountant, then owner | signed count sheet |
| خزينة مكتبة المواساة | cash box | مكتبة المواساة (Raghad) | branch manager | accountant, then owner | signed count sheet |
| خزينة سنتر Imed | cash box | قاعات Imed (Nour) | branch manager | accountant, then owner | signed count sheet |
| خزينة X Studio | cash box | استوديو X (Gilan) | branch manager | accountant, then owner | signed count sheet (XStudio balances are never posted) |
| الخزينة الرئيسية | cash box | مصروفات المقر المشتركة | accountant | owner | signed count |
| عهدة المالك النقدية / عهدة المحاسب النقدية | cash custody | nobody closes them | holder | owner | only if cash is really held |
| خزينة تطبيق BA Plus | bank-type | تطبيق BA Plus | Menna | accountant | app statement |
| محفظة InstaPay / محفظة Vodafone Cash | wallets | — | accountant | owner | wallet screenshot of the morning |

Needed from you: the counted amount per row, the **effective date** (the go-live morning), the counter's and the
approver's names, and the evidence file. Then `opening_cash.prepare({...}, "<date>")` makes one draft journal entry
against حقوق ملكية الأرصدة الافتتاحية; it refuses an account that already has entries, a wallet as a cash box, and a
negative amount. The first daily close of each box starts from this balance.

## 2. Opening stock, one sheet per library

Sheets: `opening_stock_الأزاريطة_template.csv` and `opening_stock_المواساة_template.csv` (same folder), each prefilled
with that library's own warehouses only. A row naming the other library's warehouse is refused by the checker
(`setup/check_opening_stock.py`), so the two counts cannot be mixed. Damaged stock (التالف — المواساة) is counted at
zero value. Needed per row: item code, quantity, unit counted in, approved cost per unit, cost source, count date.
The system makes one draft Stock Reconciliation (purpose Opening Stock) per branch.

Double counting with the SQL connectors: the libraries' connector imports sales and movements from a **start date**.
Set that start date to the day after the count date, and the count sheet to the stock at the close of the count day.
Nothing before the start date is imported; nothing in the count is imported again. Record the two dates on the
sheets (`count_date`) and in the connector's settings when it goes live.

## 3. What is ready, what is not

| Area | Status |
|---|---|
| Sales, payments, expenses, cash close, reopening, weekly reconciliation, counter readings, doctor ledger, dashboard | VERIFIED by 755 automated tests on the isolated site; no production write |
| Opening cash | NEEDS OWNER DATA (amounts, date, evidence) |
| Opening stock | NEEDS OWNER DATA (counts, costs) |
| Hall prices | NEEDS DECISION: tiered prices built (Hall Price Tier), awaiting deployment approval and the owner's confirmed rates |
| Library sales import | BLOCKED by the library connector (on-site metadata) |
| BA Plus fees | import built; NEEDS the app's export files |
| ERPNext test data on production | cleanup proposal in docs/audits/test-data-cleanup-proposal-2026-11-01.md, NEEDS APPROVAL |
