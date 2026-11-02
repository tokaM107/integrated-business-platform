# Release plan: hall price tiers and the XStudio sync counters (prepared 1 Nov 2026, not executed)

Two independent branches, each deployable alone, from `production` (0adfd24). Neither is pushed or deployed.

| Branch | Commits | Files | Schema | Tests |
|---|---|---|---|---|
| `fix/xstudio-sync-counters` | d8df5fa | `imederp/xstudio/sync.py`, `imederp/tests/test_xstudio_sync.py` | none | XStudio sync 38 OK |
| `feature/hall-price-tiers` | 7e6883c, c74e324, a458aa6, +boundary test | new doctype `Hall Price Tier` (json, py, js), `imederp/booking_pricing.py`, `imederp/tests/test_booking_pricing.py`, two opening-stock sheets | **one new table** (`tabHall Price Tier`), created by `bench migrate`; no existing table or record changed | pricing 31 OK, hall bookings 33 OK, booking 23 OK |

Behaviour after the pricing release, with **no tier entered**: identical to today (a hall is priced per hour from
HALL-HOUR's Item Price; with none set, a fixed-rent booking is refused). Prices become active only when the owner
creates a Hall Price Tier record per hall and price list. Tier mapping proposed, pending the owner: قاعة 1 → 800 /
1,600 / 600; قاعة 3, 4, 6 → 200 / 350 / 125; price list Standard Selling.

## Steps (either branch; both in one go is fine)

1. **Backup**: `bench --site frontend backup --with-files` in the backend container; `gzip -t` / `tar -t` the set; note the name. The nightly off-server snapshot must show OK for the day.
2. **Merge and push**: fast-forward `production` with the branch (`git merge --ff-only`), push.
3. **Deploy**: Coolify → Redeploy (owner's click or an API token). About 3 minutes of restart; the XStudio cron resumes at the next 10-minute tick (imports are idempotent).
4. **Migrate**: `bench --site frontend migrate` (needed for the pricing branch: creates the table; harmless for the counters branch).
5. **Verify**:
   - `bench --site frontend execute frappe.db.exists --kwargs '{"dt":"DocType","dn":"Hall Price Tier"}'` → true (pricing).
   - A dry pricing check on the live site, read-only: the halls still price "no price" for fixed rent until a tier exists.
   - Next sync log: `rows_read == inserted + updated + skipped + changed + failed` (counters).
   - Owner Dashboard band: XStudio card detail counts add up; halls card unchanged (4 active).
   - GL Entry, Sales Invoice, Payment Entry counts unchanged (0 today).
6. **Prices** (owner's explicit approval, after step 5): the owner or accountant creates the Hall Price Tier records in the UI; then one test booking in the UI for an internal course (not billable) and one fixed-rent quote on the form to read the computed amount, cancelled before confirming. No invoice is made without the "make invoice" action.

## Rollback

- Code: Coolify → Redeploy the previous deployment (ae2162c image).
- Table: the empty `tabHall Price Tier` may stay (unused by the old code) or be dropped by `bench --site frontend migrate` after removing the doctype; nothing else references it.
- Any tier records entered: delete them in the UI (no document links to them; bookings keep the amounts they were priced at).
- Data: the step-1 backup via `deploy/restore_site.sh` with `FORCE=1`, only if something beyond the dashboard definitions went wrong.
