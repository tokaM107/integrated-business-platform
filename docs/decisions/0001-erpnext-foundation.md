# Decision 0001: ERPNext as the foundation

**Status: DRAFT, not signed.** It becomes the decision of record only when the owner signs below.
Add the minutes of the owner meeting as `docs/decisions/<date>-owner-meeting.md`.

## Decision

1. The system is built on **ERPNext** (v16, see the README for the exact version).
2. Everything specific to the group is built in the custom app **`imed_erp`** on top of ERPNext, without
   changing ERPNext itself.
3. Target go-live: **mid-December 2026**.
4. The **library system** keeps running and is integrated with the new system.
5. The **studio booking system** stays the source of truth for appointments; the new system reads from it.

## Reasons

- Shown in the demo: profit and loss per activity (filtered by cost center), paper stock in sheet /
  ream / carton, and transfers between activities booked as transfers, not expenses.
- The custom parts can be built: the *Doctor Agreement* and *Book Edition* screens already exist in `imed_erp`.

## Known limits accepted

See [known-issues.md](../known-issues.md): Arabic text in charts, missing translations, and the features
to build from scratch (bookings, paper counters, mobile app, AI assistant).

## Costs

To be filled in with the owner: hosting, backups, number of users, and who pays for what.

| Item | Monthly cost | Paid by |
|---|---|---|
| Hosting | | |
| Backups | | |
| Users (count: ) | | |

## Sign-off

| Role | Name | Signature | Date |
|---|---|---|---|
| Owner | | | |
| Development team | | | |
| Development team | | | |
