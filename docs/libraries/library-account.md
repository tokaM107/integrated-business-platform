# A library's account and its screen (مكتبتي)

One shared account a library (owner, 4 Nov 2026), on a screen as simple as can be: `mowasah@imed.local` for
Mawasah. It lands on **مكتبتي** (`/desk/imed-library`), four big buttons and nothing else to find:

| Button | What it does | In the system |
|---|---|---|
| عدادات النهارده | the day's counters of the library's machines | Daily Counter Reading (once a day, as before) |
| حاجة خلصت | an ink bottle, a box of paper… finished | taken off the library's store (Stock Entry, Material Issue, posted by the system) |
| رصيد المخزون | what the library holds now | a Stock Count of its store (Periodic) |
| اطلب حاجة | ink, paper… needed | a Material Request: a purchase request for Mawasah (its store supplies the others); a transfer request Raghad approves for any other library |

Paper is counted, taken off and requested in boxes (2,500 sheets); ink in bottles and sets. The store's balances
and the account's last requests show under the buttons.

**What the account may do** (role Library Staff, `imederp/library_desk.py` `STAFF_RIGHTS`, applied by
`setup/setup_users.py`):
- **Its own documents:** the day's counters, stock counts, stock requests, for its own library and store only
  (User Permissions on its Cost Center and Warehouse).
- **No money:** no sales, ledger, payments, expenses, cash or accounts. No stock entries either: a finished item is
  taken off by the system, never more than the store holds.

**Inks:** stock items of the group أحبار (`setup/setup_inks.py`), valued at the prices of Printing Cost Settings
(Riso ink, Epson ink set). The libraries enter what they hold, and each one finished is taken off. A first count of
an item with no price is refused with a clear message. More colours are added as items of the same group, and the
screen lists them by itself. A reorder level on an item turns on ERPNext's stock alert.

## On a site (after deploying)

```
bench --site frontend migrate                       # the page مكتبتي
bench --site frontend console                       # then, in it:
  exec(open("/home/frappe/frappe-bench/apps/imed_erp/imed_erp/setup/setup_inks.py").read(), {"frappe": frappe})
  exec(open("/home/frappe/frappe-bench/apps/imed_erp/imed_erp/setup/setup_users.py").read(), {"frappe": frappe})
bench --site frontend set-password mowasah@imed.local <password>
bench --site frontend clear-cache
```

Check first that Printing Cost Settings holds the ink prices, or the inks are valued at 0 and their first count is
refused. Another library's account is one more line in `setup_users.py` USERS, with its own cost center and store.
