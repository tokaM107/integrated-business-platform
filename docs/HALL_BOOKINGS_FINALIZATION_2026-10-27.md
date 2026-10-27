# IMED hall bookings: finalisation and the sidebar redesign (27 Oct 2026)

Branch `feature/imed-hall-bookings`. Source of truth: `docs/وثيقة_متطلبات_نظام_ERP_v1.2.docx` §4.9 (HAL-01..12), its
hall data table and open questions, and `docs/requirements/v1.3-amendments.md`. Nothing was pushed, merged or
deployed; nothing was posted to the ledger; no hall was written to the live site.

## A. Requirements coverage

| Req. | Text (v1.2 §4.9) | Priority / status in the document | Built | Verified by |
|---|---|---|---|---|
| HAL-01 | Halls with capacity and equipment | Must / Confirmed | Booking Resource (Hall): capacity (required), equipment, location, buffer. **No hall exists on the site**: the document's table leaves capacity, equipment and price blank (question 15). `setup_halls.py` seeds the seven names once capacities are given. | `test_the_requirements_halls_are_seeded_by_name_only_and_never_twice`; `plan` run on frontend: 7 × "wait (capacity unknown)" |
| HAL-02 | Hourly booking with the activity, the responsible person and phone | Must / Confirmed | Purpose, Responsible Person, phone (checked as a phone); times to the minute; across midnight | `test_hall_bookings`, `test_booking` |
| HAL-03 | A price per hall, different per customer category | Must / Confirmed | Item per hall, Item Price per price list; the customer group's price list. **No hall price exists** (question 15): a fixed-rent booking is refused until the price is set; internal uses book without one. | `test_booking_pricing` (HAL-03) |
| HAL-04 | No overlapping bookings of the same hall | Must / Assumed | Overlap on exact instants with the buffer, serialised on the resource row; cancelled bookings free their time; the form says whether it is free before saving | `test_the_same_hall_at_an_overlapping_time_is_refused…`, `test_the_form_is_told_whether_the_hall_is_free…`, browser journey |
| HAL-05 | Recurring bookings (a weekly course) | Should / **Open** | Not built (the document leaves it open). | — |
| HAL-06 | Report: day, hall, attendees, admission, rent, collected, cancellations, unpaid | Must / Confirmed | Report *Hall Bookings* (+ type, doctor, hours) | `test_the_hall_bookings_report…` |
| HAL-07 | Each booking linked to the unified customer | Must / Confirmed | Customer / Renter; a doctor named on a lecture is its customer unless a renter is named | `test_a_lecture_is_billed_to_its_doctor…` |
| HAL-08 | Attendees and admission price per lecture; the total collected | Must / Confirmed | Expected Attendees (capacity check), Attendees (actual), Admission Price, Expected Revenue, Collected | `test_capacity_is_enforced…`, `test_booking_pricing` (HAL-08) |
| HAL-09 | Send the booking confirmation by WhatsApp or SMS | Must / Confirmed | **Not built**: no messaging channel is connected (known-issues, "waiting for other teams, files or credentials"). The contradiction stands: a Must with nothing to send through. | — |
| HAL-10 | Daily and weekly calendar with booked and free times per hall | Must / Confirmed | The Booking calendar on the halls (sidebar: تقويم القاعات); hall, purpose, doctor, type and status in each event; maintenance hatched; cancelled faded; the live availability message on the form | `test_the_calendar_names_the_hall…`, browser journey |
| HAL-11 | Extras beside the hall price | Should / Confirmed | Booking Extras; the halls' extras have no prices yet (Nour) | `test_booking_pricing` |
| HAL-12 | Both models, chosen per booking: fixed rent or revenue share | Must / Confirmed; v1.3: a free lecture (0 %) is accepted when the lecturer is named; a share with no lecturer is refused | Booking types fix the model; the share is typed per booking, never assumed; the revenue-share entry is posted only by the explicit action | `test_a_revenue_share_with_no_agreed_share_is_flagged_not_guessed`, `test_booking_pricing` (HAL-12, QA-14) |
| Q2 / Q13 | Halls: no deposit, no cancellation policy | answered "لا يوجد عربون" | *Confirmed* without a deposit (26 Oct); a deposit on a hall is refused | `test_the_confirmed_status_needs_no_deposit…` |
| Q15 / Q33 | Capacities, equipment, prices; the share % | **unanswered** | Nothing invented: see HAL-01, HAL-03, HAL-12 | — |

Contradictions and gaps to decide (owner): HAL-09 (Must, no channel); HAL-05 (open); the seven halls' numbers are
also XStudio's room ids (X Studio — Hall 1, 3, 4, 5, 6, 8) — if they are the same rooms, a studio booking and a hall
booking of the same room do not block each other today (bookings question 1).

## B. The hall booking workflow, as built

1. Sidebar **حجوزات قاعات IMED → قاعات IMED**: the halls, with capacity and location in the list; a hall's form has
   **احجزي القاعة دي** and **التقويم**.
2. A new booking shows four steps. Choose the hall; the day; **من الساعة / لحد الساعة**. The form answers at once:
   «القاعة فاضية في الوقت ده.» or «القاعة دي محجوزة بالفعل في الوقت اللي اخترته. جرّبي معاد تاني.» followed by the
   booking that has the time.
3. **نوع الحجز** decides what else is asked: purpose and responsible person always (not on a maintenance block);
   the doctor, the course, the expected attendees per type; the rental model only for an internal course or an
   external lecturer; no money fields on an internal use or a maintenance block. A doctor becomes the customer.
4. Save: the server prices it (fixed rent = the hall's price × hours; nothing for a not-billable one), checks the
   overlap again (same rule, same words) and the capacity.
5. **تأكيد الحجز** (no deposit) → مؤكد. **تغيير الموعد** opens the day and times; **إلغاء الحجز** asks the reason;
   a cancelled booking frees its time. **انتهى الحجز** after the start: records that it happened, posts nothing.
6. After completion, **عمل الفاتورة** or **تسجيل المحصَّل** (revenue share) posts, once, after the amounts are checked.

## C. The real halls (not written)

From the requirements' table "بيانات القاعات (للاستيفاء)", in its order: قاعة 1, قاعة 3, قاعة 4, قاعة 5, قاعة 6,
قاعة 7, قاعة 8 (no قاعة 2 in the table). Every other column is "……………………".

| Category | Records |
|---|---|
| Exists on the site | none (the only resources are XStudio's mirrored rooms and the studio's packages) |
| Would be inserted | 7 Booking Resources: name as above, type Hall, cost center `قاعات Imed - MMG`, item `HALL-HOUR` (exists, **no Item Price**), capacity **unknown**, equipment **unknown**, location empty, buffer 0 |
| Blocked | all 7: a hall needs its capacity (HAL-01); `setup_halls.plan()` reports "wait (capacity unknown)" for each |

To write them, after Nour's answer: `bench --site frontend execute imed_erp.imederp.setup_halls.run --kwargs
"{'capacities': {'قاعة 1': 40, …}}"` (only the halls named get written; running twice changes nothing). Prices
are Item Prices on `HALL-HOUR` (or one item per hall when prices differ), never typed on a booking.

## D. The sidebar

Owner Dashboard (لوحة المالك) · **حجوزات قاعات IMED**: تقويم القاعات, حجوزات القاعات, قاعات IMED, تقرير حجوزات
القاعات · **حجوزات استوديو التصوير**: تقويم الاستوديو, حجوزات الاستوديو, باقات ساعات الاستوديو, عملاء الاستوديو,
خدمات الاستوديو · **المكتبات**: عدادات اليوم, طباعة اليوم, عدادات الورق · **المخزن**: طلبات الخامات, صرف الخامات,
تنبيهات إعادة الطلب, الجرد, فروقات الجرد, تسجيلات التالف, مبيعات التالف · **الدكاترة والكتب**: اتفاقيات الأطباء,
إصدارات الكتب, كشف حساب الطبيب, دفتر حسابات الأطباء, مستحقات الأطباء, مديونيات الأطباء, الإصدارات اللي ماتباعتش,
نصيب المالك · **كورسات BA+**: الكورسات, اشتراكات التطبيق, رسوم المنصة · **الحسابات والخزنة**: إقفال الخزينة, تسليم
نقدية, مراجعة الخزينة الأسبوعية, فرق خزينة, قائمة المصروفات, المصروفات المتكررة, تحويل بين الأنشطة · **التقارير**:
الإيراد حسب الفترة, الربح قبل وبعد مصروفات المقر, الربح حسب النشاط, رصيد كل خزينة, حركة الخزائن, المستحقات,
المستحق لنا, تقرير المصروفات, التحويلات, المخزون والورق · **الإعدادات**: باقات وخدمات الحجز, إعدادات XStudio, متابعة
الربط, سجلات الاستيراد, إعدادات تقفيل الخزينة, المصروفات, الطباعة, الفترات الأكاديمية, شرايح رسوم المنصة.

70 items, 61 links, no duplicate target with the same filter, every target verified to exist on the site
(`test_the_sidebar_is_grouped_by_workflow…`; the owner's browser session opened all 61). Visibility: Frappe shows
a DocType, Report or Workspace link only to a user who may read it; the two calendar URLs are hidden by
`imed_desk_fixes.js` from anyone who may not read bookings (HR sees neither group's pages). Both branch managers
see both booking groups because both may read bookings; what they see inside is their own business's (user
permissions on the cost center): the studio's manager sees no hall booking and may not book a hall.

## E. Browser verification (`tests/e2e/halls_27oct.js`, 57 checks, all passing)

`docs/hall-screens/`: `sidebar-owner.png`, `sidebar-nour.png`, `sidebar-gilan.png`, `sidebar-accountant.png`,
`sidebar-hr.png`, `owner-dashboard-halls.png` (frontend, read-only); `demo-halls-list.png`, `demo-hall-form.png`,
`demo-booking-steps.png`, `demo-booking-free.png`, `demo-booking-internal-course.png`, `demo-booking-saved.png`,
`demo-booking-confirmed.png`, `demo-booking-clash-live.png`, `demo-booking-clash-refused.png`,
`demo-booking-reschedule.png`, `demo-booking-cancelled.png`, `demo-hall-calendar.png`,
`demo-hall-bookings-list.png`, `demo-gilan-hall-list-empty.png`, `demo-owner-dashboard-halls.png`,
`demo-booking-phone.png` (the demo site, with a demo hall «قاعة تجريبية (تجريبي)» made there; nothing on frontend).
`results.json` and `sidebar-by-role.json` hold the checks and each role's items.

## F. Financial safety

`booking_accounts.complete()` made the Sales Invoice (and the revenue-share Journal Entry) the moment a billable
booking was saved as Completed (approved for bookings on 20 Oct 2026, known-issues 4 and 11). The requirements
never state that completing a **hall** booking makes its invoice (§4.9 speaks of prices, models, attendees and
collection; ACC-04 of deposits linked to the booking). So, for halls only, `Booking.on_update` calls `complete()`
only when `make_booking_invoice` asked for it: *Mark Completed* posts nothing; *Make Invoice* / *Post the Collected
Amount* posts once, after a confirmation that names the amount and the share. Nothing was lost: the booking keeps
its status, prices, attendees and share; the studio's manual bookings keep the 20 Oct behaviour; imported
bookings never post. **Owner approval needed** to keep this (or to restore automatic posting for halls).

No percentage, price, hall, lecturer or agreement was invented; the lecturer's share stays typed per booking.

## G. Tests

- `test_hall_bookings`: 33 (7 new: explicit posting, availability, doctor as customer, calendar titles, sidebar
  integrity against the site, the owner's Arabic labels, the hall seed plan).
- `test_booking_pricing`: 26 (its `complete` helper now posts a hall explicitly); `test_booking`: 23.
- Full suite `scripts/run_tests.sh --app imed_erp`: **748 passed, 1 skipped** (27 Oct 2026, ~3 min).
- Browser: 57 checks (above).

## H. Git

Branch `feature/imed-hall-bookings`, on top of `3096480`. No push, no merge. No secrets, backups or binaries added
(the library's `.exe`/`.rar`/`.html` files in the working tree stay untracked).

## I. Exact steps to try it

1. Log in as nour (or the owner) at http://localhost:8080. Sidebar: **حجوزات قاعات IMED → قاعات IMED** → *+ Add*: a
   hall needs its name, cost center `قاعات Imed - MMG`, item `HALL-HOUR` and its capacity (ask Nour; or do it on the
   demo site, which already has «قاعة تجريبية (تجريبي)»).
2. On the hall: **احجزي القاعة دي**. Day, من الساعة, لحد الساعة → the green line «القاعة فاضية في الوقت ده».
3. نوع الحجز = كورس أو محاضرة داخلية; الغرض; اسم المسؤول; التليفون; الدكتور → **حفظ**: مبدئي, الرسوم: لا يوجد.
4. **تأكيد الحجز** → مؤكد. New booking, same hall, overlapping time → the red line, and on save the same message.
5. **تغيير الموعد**; **المزيد → إلغاء الحجز** with a reason → ملغي; the time is free again.
6. Owner → لوحة المالك → card حجوزات قاعات IMED counts the day; **تقويم القاعات** shows the week.
7. Money: a Fixed-fee Rental needs an Item Price on `HALL-HOUR` first; after **انتهى الحجز**, **عمل الفاتورة**
   posts the invoice (nothing before that).
