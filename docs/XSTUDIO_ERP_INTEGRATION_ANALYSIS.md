# XStudio × IMED ERP — تحليل التكامل الكامل (Discovery, API Audit, Gap Analysis, Plan)

> **حالة الوثيقة:** مرحلة بحث وتخطيط فقط (Read-only discovery). لم يُكتب أي كود تكامل ولم يُعدَّل أي من النظامين.
> **تاريخ التحليل:** 2026-10-24
> **اللغة:** الشرح بالعربية، المصطلحات التقنية وأسماء الملفات والحقول والـ API بالإنجليزية.
> **مصادر الكود:**
> - XStudio: المستودع المحلي `/Users/tokamohamed/Downloads/xstudio-` (origin: `https://github.com/Mohamedm102/xstudio-`)، الفرع `main`، آخر commit `44d3b8a07956842accd75816ed2f38a18930538b` بتاريخ 2026-10-19 ("Add files via upload"). التحليل مركَّز على المجلد `xstudio-platform/` كما طلب مطوّر XStudio.
> - IMED ERP: المستودع المحلي `/Users/tokamohamed/Downloads/integrated-business-platform` (الفرع `main`، آخر commit `6ebac7d`).
>
> كل مسار ملف لـ XStudio في هذه الوثيقة نسبي إلى `xstudio-platform/` إلا إذا ذُكر غير ذلك. كل مسار ملف لـ ERP نسبي إلى جذر مستودع `integrated-business-platform`.

---

## 1. Executive Summary (الملخص التنفيذي)

**ما هو XStudio فعلياً؟** تطبيق Node.js/Express 5 صغير (ملف routes واحد بـ 1,245 سطر) فوق PostgreSQL 16، مع واجهة HTML/JS ثابتة بدون build step. يدير 6 قاعات تصوير (Halls 1, 3, 4, 5, 6, 8) في استوديو X Studio بالإسكندرية: حجوزات بالساعة، باقات ساعات مسبقة الدفع مع خصم تلقائي، دفعات نقدية/تحويل/InstaPay مسجَّلة يدوياً، إشعارات WhatsApp (dev driver فقط فعلياً) وTelegram، تقارير أسبوعية لنسب المصورين، وتصدير Excel.

**أهم النتائج:**

1. **لا يوجد أي API مخصّص للتكامل** (لا webhooks، لا `updated_at` filter، لا pagination، لا service account). كل الـ endpoints مبنية لواجهة الموظفين والعملاء. مع ذلك، الـ endpoints الموجودة للقراءة (`GET /api/bookings`, `GET /api/customers/:id/packages`, `GET /api/admin/export`) **كافية لبناء MVP بالـ polling** من جهة ERP بشرط إضافة تعديلات صغيرة في XStudio (فلتر `updatedSince`، رفع حد الـ 500 سجل، إرجاع `payments`).
2. **XStudio يملك معرّفات مستقرة (UUID v4)** لكل الكيانات المهمة: `bookings.id`, `customer_packages.id`, `package_usage.id`, `payments.id`, `users.id` — وهذا أساس ممتاز لمنع التكرار في ERP (`external_id` + `source_system`).
3. **`bookings.updated_at` موجود ومُحدَّث بـ trigger**، لكن **`payments` و`package_usage` و`customer_packages` ليس لها `updated_at`**؛ الـ `payments` و`package_usage` append-only (لا تُعدَّل أبداً) فيستفاد من `created_at`، أما `customer_packages` فتُعدَّل مباشرة (`PATCH /customer-packages/:id` يغيّر `hours_remaining`) بدون أثر زمني → **فجوة يجب إغلاقها في XStudio**.
4. **نموذج XStudio المالي أبسط من ERP**: لا فواتير محاسبية (الـ "invoice" PDF مجرد عرض للحجز)، لا حسابات، لا مراكز تكلفة. المبالغ على مستوى الحجز (`price_total`, `amount_due`, `amount_paid`, `payment_status`) وسجل دفعات (`payments`) بدون ربط بخزنة أو فرع. لذلك **ERP هو مصدر الحقيقة المالي، وXStudio مصدر الحقيقة التشغيلي** (المواعيد، الحالة، استهلاك الباقات).
5. **قواعد عمل مختلفة عن المتوقَّع في ERP** (تفاصيل في §7): XStudio *له* ساعات عمل لكل قاعة (`open_minute`/`close_minute`، افتراضياً 10:00–24:00) بعكس قاعدة "لا ساعات عمل ثابتة"; الحجز الـ`hall_rental` في XStudio هو إيجار قاعة تصوير بعربون 50% وليس حجز قاعة محاضرات بنموذج revenue-share; لا وجود لمفهوم "نسبة المحاضر" — الموجود هو **نسب المصورين** (photographers' cut) الأسبوعية; الحجز قد يُنشأ بحالة `confirmed` مباشرة أو `pending`، والدفع لا يرتبط بالحالة.
6. **التوصية:** تكامل Hybrid يبدأ بـ **polling من ERP كل 5–10 دقائق** على endpoints XStudio الحالية (مع 3 تعديلات صغيرة في XStudio)، ثم إضافة **webhook اختياري** لاحقاً لتقليل زمن الانتظار. الاستيراد يمر عبر **Staging/Mapping layer في ERP** ولا يُنشئ أي Sales Invoice أو Payment Entry إلا بقاعدة صريحة لكل حدث (§12).
7. **MVP** (التفاصيل §15): مزامنة اتجاه واحد XStudio → ERP لـ: العملاء/المدرّسين، الحجوزات (كل الأنواع) مع حالاتها، الباقات وسجل الاستهلاك، والدفعات كـ **سجلات مرآة (mirror records) غير محاسبية** + تقرير مطابقة. **لا يتم إنشاء Payment Entry أو Sales Invoice تلقائياً في MVP** إلا بعد قرار المالك على القواعد المحاسبية (§21).

---

## 2. Repository and Architecture Overview (نظرة على المستودع والمعمارية)

### 2.1 التحقق من الوصول وحالة المستودع

| البند | القيمة |
|---|---|
| Remote | `https://github.com/Mohamedm102/xstudio-` (مستنسخ محلياً في `~/Downloads/xstudio-`) |
| الفرع المحلَّل | `main` |
| آخر commit | `44d3b8a07956842accd75816ed2f38a18930538b` — 2026-10-19 17:47 (+03) — "Add files via upload" |
| فروع أخرى | `origin/half-hour-booking` (آخر commit `3d40869`، 2026-09-07، **غير مدمج**) |
| المجلد المطلوب | موجود باسم **`xstudio-platform/`** (بشرطة، ليس مسافة) |

**ملاحظة مهمة عن النسخ المكرَّرة:** المستودع يحوي **ثلاث نسخ** من الكود:

| النسخة | الحالة | الدليل |
|---|---|---|
| `xstudio-platform/backend/src/*` + `xstudio-platform/frontend/public/*` | **النسخة المشغَّلة (canonical)** | `backend/package.json` → `"start": "node src/index.js"`؛ `src/index.js:4` يستورد `./routes`؛ `routes.js:6` يستورد `./services/bookingService` |
| جذر المستودع `backend/`, `frontend/`, `docs/` | **نسخة قديمة** (OLD-CODE.md يقول إنها حُذفت 2026-09-06 لكنها عادت مع commit "Add files via upload") | `OLD-CODE.md:12-30`؛ `diff -rq` يُظهر اختلافات في كل الملفات تقريباً |
| ملفات مفردة في `xstudio-platform/` مباشرة: `routes.js`, `index.js`, `app.js`, `admin.html`, `schedule.html`, `index.html` | **نسخ طائشة (stray)** — أحدث قليلاً من `backend/src` (مثلاً تضيف security headers في `index.js:13-21` وتسجّل `acceptTerms` في `routes.js:57-58`) لكنها **غير قابلة للتشغيل** من مكانها (`index.js` يستورد `./db` غير الموجود هناك) | `diff routes.js backend/src/routes.js` → فرق سطرين فقط |
| `xstudio-platform/backend/src/bookingService.js` | **نسخة قديمة** من `services/bookingService.js` (333 سطر مقابل 432، تفتقر لمنطق `svc:` والـ pricing) | لا أحد يستوردها |

> **سؤال للمطوّر (Q-X1):** هل النسخة المنشورة على `xstudioeg.com` هي `backend/src/` أم الملفات المفردة الأحدث؟ التحليل أدناه يعتمد على `backend/src/` لأنها الوحيدة القابلة للتشغيل، والاختلافات مع النسخ الطائشة ليست جوهرية للتكامل.

### 2.2 الـ Technology Stack

| الطبقة | التقنية | المصدر |
|---|---|---|
| Runtime | Node.js ≥ 20 | `backend/package.json:11` |
| Web framework | Express ^5.2.1 | `backend/package.json:16` |
| Database | PostgreSQL 16 (+ extensions `btree_gist`, `pgcrypto`) | `backend/sql/schema.sql:7-8` |
| DB access | `pg` (raw SQL، لا ORM) | `backend/src/db.js:2,32` |
| Auth | JWT (`jsonwebtoken`)، bcrypt للكلمات، صلاحية التوكن 7 أيام | `backend/src/middleware/auth.js:1-2`, `db.js:6-7` |
| Excel | `exceljs` | `backend/src/services/excelSync.js:2` |
| PDF | `pdfkit` | `backend/src/services/invoice.js:2` |
| Notifications | Telegram Bot API (fetch) + Meta WhatsApp Cloud API (driver `meta`، غير مجرَّب) | `backend/src/services/whatsapp.js:23-45, 132-144` |
| Frontend | HTML/CSS/Vanilla JS ثابت، AR/EN، بدون bundler | `frontend/public/{index.html,app.js,admin.html,schedule.html}` |
| Hosting | Railway (استدلالاً من `index.js:10,25`) + Supabase Postgres (استدلالاً من `db.js:28-31`) | `backend/src/index.js:25`, `db.js:31` |
| Tests | `node --test` + supertest (39 اختبار تكامل) + Playwright e2e | `backend/test/api.test.js`, `scripts/e2e.js` |
| Timezone | `TZ=Africa/Cairo` مفروض بالـ env؛ الأوقات تُحسب محلياً ثم تُخزَّن `timestamptz` | `db.js:8`, `services/bookingService.js:5-10` |

### 2.3 المعمارية العامة

```
Browser (index.html/app.js = العملاء · admin.html = لوحة الإدارة · schedule.html = شبكة الأسبوع للموظفين)
        │ HTTPS JSON  (Authorization: Bearer <JWT>)
        ▼
Express app  (backend/src/index.js)  ── static files + /api/* + /api/health
        │
        ├── routes.js (كل الـ endpoints في ملف واحد، ~70 route)
        │     ├── middleware/auth.js   (authRequired, requirePerm, audit → audit_logs + Telegram للمالك)
        │     ├── services/bookingService.js (availability, createBooking, cancel, reschedule — transactions + FOR UPDATE)
        │     ├── services/whatsapp.js (رسائل العملاء، Telegram للإدارة، reminders، digests)
        │     ├── services/excelSync.js (upsert في ملف xlsx + تصدير كامل)
        │     ├── services/invoice.js  (PDF للحجز)
        │     └── studioConfig.js      (أسعار الخدمات وعروضها من env + جدول settings، cache 30s)
        ▼
PostgreSQL (11 جدول) — القيود الجوهرية في الـ DB: EXCLUDE no_double_booking، CHECK hours_remaining >= 0
```

**مهام خلفية داخل العملية نفسها (in-process timers)** — `backend/src/index.js:110-130`:
- كل ساعة: `runDueReminders()` (تذكير 24 ساعة).
- كل 6 ساعات: `runPackageAlerts()` (باقات على وشك الانتهاء).
- كل 30 دقيقة: `runPaymentReminders()` (حجز انتهى وعليه مستحقات → Telegram).
- كل دقيقة: فحص الساعة 10:00 و22:00 بتوقيت القاهرة لإرسال جدول اليوم/الغد على Telegram.
- عند الإقلاع: `ensureSchema()` (ALTER/CREATE IF NOT EXISTS) ثم `backfillOrphanBookings()` (ربط الحجوزات القديمة بعملاء حسب الهاتف).

**لا توجد طبقة Jobs/Queue، ولا Webhooks صادرة، ولا OpenAPI.** التوثيق في `docs/api.md` **قديم وناقص** (يذكر cancel policy 12h بينما الكود 24h — `db.js:10`؛ لا يذكر `/blocks`, `/photographers`, `/reports/week`, `/reports/unpaid-past`, `/admin/customers/*`, `/customer-packages/*`, `/bookings/:id/apply-package`, `/bookings/:id/amount-due`, `/admin/settings/*`).

### 2.4 نموذج البيانات (ERD) — من `backend/sql/schema.sql` + `index.js:ensureSchema`

| الجدول | المفتاح | الأعمدة المهمة للتكامل | ملاحظات |
|---|---|---|---|
| `users` (`schema.sql:24-36`) | `id uuid` | `role` enum(`super_admin,manager,reception,accountant,customer`)، `name`, `phone text UNIQUE NOT NULL`, `email UNIQUE`, `notes`, `address`, `is_active`, `created_at` | **العملاء والموظفون في جدول واحد**. المدرّس = `users.role='customer'`. الدور `viewer` مستعمل في الكود (`auth.js:25`, `routes.js:38`) **لكنه غير موجود في enum** `user_role` في `schema.sql:12` ولا في `ensureSchema` → إنشاء مستخدم viewer سيفشل على DB منشأة من `schema.sql` ما لم يُعدَّل الـ enum يدوياً. لا `updated_at`. |
| `halls` (`:39-50`) | `id int` (1,3,4,5,6,8) | `name`, `price_per_hour numeric(10,2)`, `open_minute`, `close_minute`, `equipment jsonb`, `images`, `videos`, `is_active`, `has_screen`, `has_whiteboard` | ساعات عمل لكل قاعة. |
| `package_templates` (`:53-62`) | `id uuid` | `name`, `hours numeric(6,2)`, `price`, `validity_days` (NULL = لا تنتهي), `category` (`general|smart|reels|podcast|hall_rental|location_rental|svc:<id>`), `is_active`, `created_at` | كتالوج الباقات. |
| `customer_packages` (`:64-76`) | `id uuid` | `customer_id → users`, `template_id`, `name`, `hours_total`, `hours_remaining` (CHECK ≥ 0), `price`, `payment_status` enum(`unpaid,partial,paid,refunded`), `purchased_at`, `expires_at` | **باقة مشتراة لعميل**. لا `updated_at`. لباقات الـ reels الوحدة = ريل وليس ساعة (`bookingService.js:246-249`). |
| `bookings` (`:79-113` + `:180-193,218` + `index.js:50,57`) | `id uuid` | `hall_id`, `customer_id` (nullable), `customer_name`, `customer_phone`, `starts_at`, `ends_at` (timestamptz), `hours` (**generated** = (ends-starts)/3600), `price_total`, `package_id`, `hours_deducted`, `amount_due`, `amount_paid`, `payment_status`, `status` enum(`pending,confirmed,completed,cancelled`), `session_type`, `booking_type` text (`session|smartboard|reels|podcast|hall_rental|location_rental|svc:<id>[#n]`), `screen_size` (75/86), `cameras` (1-3), `deposit_due`, `price_pending bool`, `notes`, `created_by`, `created_at`, **`updated_at` (trigger `set_updated_at`, `:168-174`)**, `cancelled_by` (`staff|customer`), `cancel_note`, `photographer_id` | القيد `no_double_booking EXCLUDE USING gist (hall_id =, tstzrange(starts_at,ends_at,'[)') &&) WHERE status<>'cancelled'` (`:110-112`). |
| `package_usage` (`:118-125`) | `id uuid` | `package_id`, `booking_id`, `hours` (موجب = خصم، سالب = استرداد), `reason` (`booking|cancel_refund`), `created_at` | **Ledger** append-only لاستهلاك الباقات. |
| `payments` (`:128-137`) | `id uuid` | `booking_id` أو `package_id` (CHECK أحدهما)، `amount` (سالب للاسترداد), `method` text (`cash|transfer|instapay|other|refund`), `recorded_by`, `created_at` | **Ledger** append-only للدفعات. لا يوجد `updated_at` ولا حذف. |
| `blocks` (`:198-208`) | `id uuid` | `hall_id`, `starts_at`, `ends_at`, `reason`, `created_by` | ساعات مقفولة (صيانة/إجازة). |
| `settings` (`:187-191`) | `key text` | `value jsonb`, `updated_at` | مفاتيح: `rates`, `offers`, `msg_templates`. |
| `photographers` (`:212-217`) | `id uuid` | `name`, `is_active` | من صوَّر الجلسة. |
| `week_closings` (`:220-225`) | `week_start date` | `data jsonb` (`{base,pcts,lines,totals,notes,total_cut}`), `closed_by`, `closed_at` | **قفل حساب الأسبوع ونسب المصورين** (snapshot). |
| `notifications` (`:140-153`) | `id uuid` | `user_id`, `audience`, `channel`, `template`, `title`, `body`, `status`, `phone`, `sent_at` | صندوق الرسائل الصادرة. |
| `audit_logs` (`:156-165`) | `id bigserial` | `user_id`, `action`, `entity`, `entity_id`, `meta jsonb`, `created_at` | **سجل تدقيق متسلسل** — يمكن استعماله كـ change feed للتكامل (انظر §9). |

**العلاقات:** `users 1─∞ bookings`, `users 1─∞ customer_packages`, `halls 1─∞ bookings`, `package_templates 1─∞ customer_packages`, `customer_packages 1─∞ package_usage`, `customer_packages 1─∞ bookings` (عبر `package_id`), `bookings 1─∞ payments`, `customer_packages 1─∞ payments`, `photographers 1─∞ bookings`.

### 2.5 الفرع غير المدمج `origin/half-hour-booking`

يضيف (بتاريخ 2026-09-07، قبل إضافة المصورين وحساب الأسبوع على `main`):
- حجوزات بنصف ساعة (`?step=30` في availability) ووقت تحضير (prep time) لكل قاعة.
- `GET /api/dashboard` (قراءة فقط: حجوزات اليوم بالحالة، القاعات المستعملة الآن، الساعتين القادمتين، المستحقات) و`GET /api/reports/heatmap`.
- **غير منشور وغير مدمج** → لا يُعتمد عليه في التكامل، لكنه يبيّن أن المطوّر مستعد لإضافة endpoints قراءة مجمَّعة.

---

## 3. XStudio Feature Inventory (جرد كامل للميزات)

**مفتاح الحالة:** ✅ Implemented (كود + اختبار) · 🟡 Partial · 🖥 UI Only · ❓ Not Verified live · ❌ Not present.
**مفتاح الصلة بالتكامل (Integration relevance):** 🔴 High · 🟠 Medium · ⚪ Low.

### 3.1 Studio Management (إدارة الاستوديو)

| # | Feature | Business purpose | UI | Backend | Database | Status | Important rules | Rel. | Source evidence |
|---|---|---|---|---|---|---|---|---|---|
| S1 | Studio booking creation (customer self-service) | العميل يحجز قاعة/خدمة بالساعة | `index.html` booking widget, `app.js` | `POST /api/me/bookings` → `handleCreateBooking` → `bookingSvc.createBooking` | `bookings`, `package_usage`, `customer_packages` | ✅ | الحالة الابتدائية `confirmed`؛ لا يمرّ `pricing` (سعر الموقع فقط)؛ الخصم من الباقة تلقائي (أقدم باقة نشطة لنفس الفئة، خصم جزئي مسموح) | 🔴 | `routes.js:471-477`, `bookingService.js:136-342`, test `api.test.js:56` |
| S2 | Staff booking (registered or walk-in) | الموظف يحجز لعميل | `admin.html` "➕ حجز جديد لعميل", `schedule.html` quick-book | `POST /api/bookings` | `bookings`, `users` (ينشئ عميلاً بالهاتف إن لم يوجد) | ✅ | إذا أُرسل `customerId` → الحالة `pending` حتى يؤكّد العميل؛ walk-in → `confirmed`. يقبل `pricing` {mode: site/custom/per_person/pending} + screen add-on. ينشئ user تلقائياً من الهاتف (`routes.js:493-506`) | 🔴 | `routes.js:480-513`, test `:285,:309` |
| S3 | Booking calendar / weekly schedule grid | شبكة أسبوعية لكل القاعات | `schedule.html` | `GET /api/bookings?hallId&from&to&status&customerId`, `GET /api/blocks` | `bookings`, `blocks` | ✅ | **LIMIT 500** ثابت (`routes.js:582`)، لا pagination | 🔴 | `routes.js:569-584` |
| S4 | Room/hall selection + capabilities | اختيار قاعة؛ smartboard فقط في قاعات بها شاشة | `index.html` hall tabs | `GET /api/halls`, `has_screen` check | `halls` | ✅ | `has_screen` يحكم smartboard (`bookingService.js:152-156`) | 🟠 | `routes.js:357-360`, test `:796` |
| S5 | Cameras & equipment | عدد الكاميرات للبودكاست؛ 3 كاميرات مشتركة على كل القاعات | widget `camSelect` | `createBooking` | `bookings.cameras`, `halls.equipment` | ✅ | مجموع الكاميرات المتداخلة زمنياً ≤ 3 (`bookingService.js:186-200`) | 🟠 | `bookingService.js:93,186-200` |
| S6 | Teacher/customer management | إدارة العملاء (المدرّسون هم العملاء) | `admin.html` "👥 داشبورد العملاء" | `GET/POST /api/customers`, `PATCH/DELETE /api/customers/:id`, `GET /api/admin/customers/search` | `users` | ✅ | الهاتف UNIQUE؛ الحذف ممنوع إن وُجدت حجوزات/باقات | 🔴 | `routes.js:922-1015, 330-354` |
| S7 | Booking availability | الخانات الحرة بالساعة لكل قاعة/يوم | widget | `GET /api/halls/:id/availability?date=` (public) | `bookings`, `blocks`, `halls` | ✅ | خانات بـ 60 دقيقة (`config.slotMinutes`) بين `open_minute` و`close_minute` | ⚪ | `bookingService.js:16-56` |
| S8 | Overlapping booking prevention | منع التعارض | — | DB constraint → 409 | `bookings` EXCLUDE | ✅ | على مستوى الـ DB وليس الكود | 🟠 | `schema.sql:110-112`, `bookingService.js:337` |
| S9 | Booking confirmation | العميل يؤكّد حجزاً أنشأه الموظف | `app.js` "My bookings" | `POST /api/bookings/:id/confirm` | `bookings.status` | ✅ | فقط صاحب الحجز؛ فقط من `pending` | 🔴 | `routes.js:516-533` |
| S10 | Booking cancellation | إلغاء مع استرداد ساعات الباقة | customer + admin + schedule | `POST /api/bookings/:id/cancel` → `cancelBooking` | `bookings`, `package_usage`, `payments` | ✅ | العميل: قبل 24 ساعة فقط (`CANCEL_MIN_HOURS_BEFORE`, `db.js:10`); الموظف بلا قيد. يُعاد `hours_deducted` للباقة بسطر `cancel_refund`. للـ rental: استرداد كامل المدفوع إذا ≥ 24h بسطر payment سالب `method='refund'` و`payment_status='refunded'` | 🔴 | `bookingService.js:345-395`, test `:118,:333,:644` |
| S11 | Booking rescheduling | نقل الحجز لوقت آخر | admin/schedule | `PATCH /api/bookings/:id/reschedule` | `bookings.starts_at/ends_at` | ✅ | **نفس المدة فقط** (لا تغيير ساعات)؛ العميل قبل 12h | 🔴 | `bookingService.js:398-430` |
| S12 | Session start | — | — | — | — | ❌ | لا يوجد مفهوم "بدء الجلسة" | ⚪ | — |
| S13 | Session completion | إتمام الجلسة + تسجيل دفعة | admin | `POST /api/bookings/:id/complete` {amountPaid?, method?} | `bookings.status='completed'`, `payments` | ✅ | **لا يتحقق من الحالة السابقة** (يمكن إكمال حجز ملغي!) ولا من مرور الوقت؛ يضيف `amountPaid` إلى `amount_paid` | 🔴 | `routes.js:666-689` |
| S14 | Recording duration | المدة = `hours` generated من الفرق الزمني | — | — | `bookings.hours` | ✅ | دقة 2 خانة عشرية؛ المدة المخطَّطة لا المدة الفعلية (لا تسجيل زمن فعلي) | 🔴 | `schema.sql:87-88` |
| S15 | Session history | تاريخ حجوزات العميل | `app.js` My bookings; admin customer card | `GET /api/me/bookings`, `GET /api/bookings?customerId=` | `bookings` | ✅ | | 🟠 | `routes.js:586-593` |
| S16 | Staff assignment (photographer) | من صوّر الجلسة | admin "📷 المصورين" | `GET/POST/PATCH /api/photographers`, `PATCH /api/bookings/:id/photographer` | `photographers`, `bookings.photographer_id` | ✅ (لا اختبار) | | 🟠 | `routes.js:1065-1103` |
| S17 | Notifications | WhatsApp للعميل (dev driver = سجل فقط)، Telegram للإدارة | admin notifications feed | `whatsapp.js` | `notifications` | 🟡 | Meta driver مكتوب غير مجرَّب (`deployment.md:60-64`); الموظف يرسل يدوياً عبر wa.me ويعلّم `sent` | ⚪ | `whatsapp.js`, `routes.js:1209-1235` |
| S18 | Payment tracking per booking | تسجيل دفعات قبل/بعد الجلسة | admin | `POST /api/bookings/:id/pay` {amount, method, settle?}, `PATCH /api/bookings/:id/amount-due` | `bookings.amount_paid/amount_due/payment_status`, `payments` | ✅ | `settle=true` يجعل `amount_due = amount_paid` (خصم ضمني غير مسجَّل كسطر منفصل!); `amount-due` يعدّل المستحق مباشرة | 🔴 | `routes.js:536-567` |
| S19 | Recording-hour packages (templates) | كتالوج باقات | admin "🎁 الباقات"; public pricing | `GET/POST /api/package-templates`, `PATCH /api/package-templates/:id` | `package_templates` | ✅ | `category` يحدّد أي نوع حجز تغطيه | 🟠 | `routes.js:778-793, 238-263` |
| S20 | Package purchase / assignment | بيع باقة لعميل | admin | `POST /api/customers/:id/packages` {templateId \| name,hours,price,validityDays; paidAmount}, `POST /api/me/packages` (self-activation) | `customer_packages`, `payments` | ✅ | `payment_status` يُحسب من `paidAmount` مقابل `price`; دفعة `method='cash'` ثابتة عند الشراء | 🔴 | `routes.js:797-822, 882-901` |
| S21 | Package usage & remaining hours | خصم تلقائي + ledger | — | في `createBooking`/`cancelBooking`/`apply-package` | `package_usage`, `customer_packages.hours_remaining` | ✅ | ledger مكتمل: كل تغيير له سطر؛ **لكن** `PATCH /customer-packages/:id` يعدّل `hours_remaining` مباشرة **بدون سطر ledger** (`routes.js:825-845`) | 🔴 | `bookingService.js:243-331`, `routes.js:632-663` |
| S22 | Package expiration | `expires_at` من `validity_days`; تُستثنى الباقات المنتهية من الخصم | — | query filter | `customer_packages.expires_at` | ✅ | لا يوجد تغيير حالة عند الانتهاء، فقط فلتر زمني + تنبيه 7 أيام | 🟠 | `bookingService.js:253,274`, `whatsapp.js:328-338` |
| S23 | Discounts / refunds / manual adjustments | خصم ضمني (`settle`), تعديل المستحق, سعر يدوي (`pricing.custom/per_person/pending`), تعديل الباقة, حذف الباقة | admin | انظر S18, S2, S21 | | ✅ | **لا سطر "خصم" صريح**؛ الخصم = فرق بين `price_total` و`amount_due`. حذف الباقة يمسح `package_usage` كاملاً ويفكّ `bookings.package_id` (`routes.js:865-878`) → **يُفسد التاريخ** | 🔴 | `routes.js:545-549, 557-567, 865-878` |
| S24 | Recording / revenue reports | إيرادات، إشغال، مستحقات، حجوزات منتهية غير مدفوعة | admin | `GET /api/reports/{revenue,utilization,outstanding,unpaid-past}` | `payments`, `bookings` | ✅ | revenue = SUM(payments.amount) حسب `created_at` (يشمل السالب للاسترداد) | 🟠 | `routes.js:1018-1062` |
| S25 | Weekly account & photographers' cut (حساب الأسبوع) | المالك يقفل الأسبوع ويحدّد نسبة كل مصوّر لكل نوع حجز | admin "🧾 حساب الأسبوع", "💸 نسب المصورين" | `GET /api/reports/week?start=`, `PUT /api/reports/week/:start/close` | `week_closings` | ✅ (لا اختبار) | الأسبوع يبدأ السبت؛ الأساس `paid` أو `price`; النسبة لكل (مصوّر × bucket); snapshot في jsonb | 🔴 (**ميزة لم تُغطَّ في متطلبات ERP**) | `routes.js:1105-1206` |
| S26 | Blocks (ساعات مقفولة) | إقفال ساعات صيانة/إجازة | `schedule.html` | `GET/POST/DELETE /api/blocks` | `blocks` | ✅ | لا يمكن إقفال ساعة فيها حجز نشط | ⚪ | `routes.js:385-423` |
| S27 | Pricing engine & editable rates | أسعار شاشات/كاميرات/ريلز/لوكيشن + زيادة عطلة + خدمات مخصصة `svc:` | admin "💰 أسعار الخدمات", "🛠 الخدمات والعروض" | `GET /api/config` (public), `GET/PUT /api/admin/settings/rates`, `GET/PUT /api/admin/settings/offers` | `settings` | ✅ | السعر يُحسب server-side دائماً؛ cache 30 ثانية | 🟠 | `studioConfig.js`, `routes.js:113-226` |
| S28 | Excel sync/export + customer sheet import | تصدير الحجوزات وقاعدة العملاء؛ استيراد عملاء وباقات من شيت | admin | `GET /api/excel/export`, `POST /api/admin/customers/import` | ملف xlsx + `users`, `customer_packages`, `payments` | ✅ | one-way؛ الاستيراد يُنشئ باقات بـ `expires = start + 365d` ودفعة `method='other'` | 🟠 | `excelSync.js`, `routes.js:266-327` |
| S29 | Invoice PDF | PDF لبيانات الحجز | customer + admin | `GET /api/bookings/:id/invoice` | — | ✅ | **ليست فاتورة محاسبية** (لا رقم تسلسلي، لا ضرائب، تُولَّد كل مرة) | ⚪ | `invoice.js` |
| S30 | Full DB JSON export | نسخة احتياطية JSON لكل الجداول (11 جدول) | admin "نسخة احتياطية" | `GET /api/admin/export` | all | ✅ | super_admin/manager فقط؛ **يُخرج `password_hash`** للمستخدمين (`SELECT *`) | 🟠 (مفيد للاستيراد الأولي، خطِر أمنياً) | `routes.js:94-109` |
| S31 | Audit log | سجل كل الأفعال | — | `audit()` | `audit_logs` | ✅ | غير معروض بـ API (لا endpoint لقراءته) | 🟠 | `auth.js:106-119` |
| S32 | Staff accounts & RBAC | 5 أدوار + صلاحيات | admin | `POST/GET/PATCH /api/admin/users` | `users` | ✅ | `viewer` غير موجود في enum الـ DB (انظر §2.4) | 🟠 | `auth.js:7-27`, `routes.js:705-766` |

### 3.2 Hall Management (إدارة القاعات)

**نتيجة جوهرية:** "Hall" في XStudio تعني **قاعة تصوير داخل الاستوديو** (6 قاعات مرقَّمة)، و`booking_type='hall_rental'` يعني **إيجار قاعة التصوير بدون طاقم** (location/hall rental بعربون 50%). **لا يوجد في XStudio أي مفهوم لقاعات المحاضرات، المحاضرين، عدد الحضور، أو تقاسم الإيراد مع المحاضر** كما في متطلبات HAL في ERP.

| # | Feature (HAL) | XStudio status | Evidence / notes |
|---|---|---|---|
| H1 | Hall reservations | 🟡 موجود كـ `booking_type in ('hall_rental','location_rental')` على نفس جدول `bookings` | `bookingService.js:71-72, 297-298` |
| H2 | Hall types & capacity | ❌ لا `capacity`؛ `halls.equipment/has_screen/has_whiteboard` فقط | `schema.sql:39-50` |
| H3 | Lecture bookings | ❌ لا مفهوم محاضرة/كورس | — |
| H4 | Booking dates & durations | ✅ نفس `starts_at/ends_at/hours` | — |
| H5 | Lecturer information | ❌ (العميل = `users` فقط) | — |
| H6 | Hall availability | ✅ نفس S7 | — |
| H7 | Booking conflicts | ✅ نفس S8 | — |
| H8 | Attendee counts | 🟡 `pricing.mode='per_person'` يرسل `people` و`perPerson` **لكن لا يُخزَّن `people`** — يُخزَّن فقط في `audit_logs.meta` (`routes.js:463-465`) و`price_total` | `bookingService.js:217-219` |
| H9 | Fixed rental pricing | ✅ `price_total` = ساعات × `halls.price_per_hour` (أو `locationRate` 450/h) أو سعر يدوي `custom` | `bookingService.js:123-129, 213-222` |
| H10 | Revenue-sharing arrangements (مع المحاضر) | ❌ **غير موجود**. الموجود: نسب المصورين الأسبوعية (S25) وهي عكس الاتجاه (حصة الموظف من إيراد الاستوديو) | `routes.js:1105-1206` |
| H11 | Lecturer share calculations | ❌ | — |
| H12 | Payment collections | ✅ `deposit_due` = 50% (محسوب، غير مُلزم)، `POST /bookings/:id/pay` | `bookingService.js:70, 297-298`, `routes.js:536-554` |
| H13 | Hall cancellation | ✅ مع استرداد تلقائي إذا ≥ 24h (سطر payment سالب) | `bookingService.js:366-376` |
| H14 | Booking completion | ✅ نفس S13 | — |
| H15 | Financial reports | 🟡 revenue/outstanding/unpaid-past عامة لكل الأنواع | `routes.js:1018-1062` |
| H16 | Utilization reports | ✅ `GET /api/reports/utilization?from&to` لكل قاعة | `routes.js:1026-1038` |

### 3.3 ميزات إضافية اكتُشفت ولم تكن في اعتبار ERP

| Feature | وصف | أهمية للتكامل |
|---|---|---|
| **حساب الأسبوع ونسب المصورين** (S25) | المالك يقفل كل أسبوع (من السبت) ويحدّد نسبة لكل مصوّر لكل نوع خدمة، على أساس المدفوع أو السعر؛ يُخزَّن snapshot. هذا **مصروف/التزام تجاه المصورين** يجب أن يظهر في ERP (مستحقات للموظفين) | 🔴 |
| **الحجوزات بسعر معلَّق** `price_pending` | حجز بلا سعر حتى يتفق الاستوديو مع العميل؛ `price_total=0`, `amount_due=0` → لا يجب أن يُنشئ ERP فاتورة بصفر | 🔴 |
| **خدمات مخصّصة `svc:<id>#<n>`** | نوع الحجز قد يكون نصاً ديناميكياً يرجع إلى عنصر في `settings.offers`؛ العنوان البشري يتغيّر مع الوقت | 🔴 (الـ mapping إلى Item في ERP يجب أن يكون جدولاً قابلاً للتعديل وليس hard-coded) |
| **باقات الريلز** | الوحدة "ريل" وليس ساعة، مخزَّنة في نفس الأعمدة `hours_*` | 🔴 (خطأ تفسير = خطأ رصيد) |
| **زيادة العطلة** `weekendSurcharge` | % تُضاف على يوم الجمعة (قابلة للتعديل) | 🟠 (السعر يأتي محسوباً من XStudio؛ ERP لا يعيد الحساب) |
| **الحجز بالنيابة ينشئ عميلاً تلقائياً** بالهاتف | أي walk-in برقم هاتف يصبح `users` row | 🔴 (مطابقة الهوية بالهاتف) |
| **Blocks** | ساعات مقفولة ليست حجوزات | ⚪ |
| **Telegram alerts للمالك** | تغييرات الأسعار/الباقات/الصلاحيات تُبلَّغ للمالك | ⚪ |
| **التصدير الكامل JSON** | مصدر عملي للاستيراد الأولي (initial import) | 🟠 |

### 3.4 التحقق من قواعد العمل الحرجة المذكورة في طلب التحليل

| القاعدة المطلوبة | سلوك XStudio الفعلي | متوافق؟ |
|---|---|---|
| "لا ساعات عمل ثابتة للاستوديو" | **كل قاعة لها `open_minute/close_minute`** (افتراضي 10:00–24:00، قابلة للتعديل عبر `PATCH /halls/:id`)؛ الحجز خارجها يُرفض بـ 422 (`bookingService.js:180-182`) | ❌ جزئياً — يمكن ضبطها 0–1440 لكن القيد موجود |
| "المدرّس يحجز حين يوجد slot متاح" | ✅ availability بالساعة الكاملة فقط (`slotMinutes=60`)؛ نصف الساعة على فرع غير مدمج | 🟡 |
| "يشتري 30 ساعة ويستهلكها على جلسات" | ✅ `customer_packages.hours_total/hours_remaining` + `package_usage` ledger، خصم جزئي، استرداد عند الإلغاء | ✅ |
| "تتبّع المتبقي بدقة" | ✅ عدا ثغرتين: `PATCH /customer-packages/:id` يغيّر الرصيد بلا ledger؛ `DELETE /customer-packages/:id` يمحو الـ ledger | 🟡 |
| "حجوزات القاعات بإيجار ثابت أو تقاسم إيراد" | إيجار ثابت ✅ (أو سعر يدوي/للفرد)؛ **تقاسم الإيراد مع المحاضر ❌ غير موجود** | ❌ |

---

## 4. Existing REST API Endpoints (جرد كامل)

**Base URL:** `/api` (`index.js:32`). **Auth:** `Authorization: Bearer <JWT>`؛ التوكن من `POST /api/auth/login` (هاتف أو إيميل + كلمة سر)، صلاحيته **7 أيام** (`db.js:7`) ولا يوجد refresh token ولا API keys. **الأخطاء:** `{ "error": "<نص بشري، غالباً عربي>" }`. **لا pagination في أي endpoint** (حدود ثابتة: 500/200/100/90/8). **لا فلتر `updated_at` في أي endpoint.** **لا ETag/If-Modified-Since.**

**مفتاح "ERP Usage":** READ = يقرأه ERP في المزامنة · WRITE = قد يكتبه ERP (غير موصى به في MVP) · N/A.
**مفتاح "Status":** ✅ Integration-ready · 🔧 Requires modification · ⚠️ Insecure/insufficient · ➕ Missing (مقترح في §5) · ⚪ Not required.

### 4.1 Auth & Accounts

| Method | Endpoint | Purpose | Auth / Perm | Request | Response | ERP Usage | Status | Source |
|---|---|---|---|---|---|---|---|---|
| POST | `/api/auth/register` | تسجيل عميل | public (rate-limited 20/15min/IP) | `{name, phone, password, email?}` | `201 {token, user}` / 409 / 422 | N/A | ⚪ | `routes.js:44-63` |
| POST | `/api/auth/login` | دخول | public (rate-limited) | `{phone?\|email?, password}` | `200 {token, user{id,role,name,phone}}` / 401 | **تسجيل دخول حساب الخدمة** | 🔧 (يحتاج دور `integration` للقراءة فقط + توكن طويل/API key) | `routes.js:65-76` |
| POST | `/api/me/password` | تغيير كلمة السر | auth | `{oldPassword,newPassword}` | `{ok}` | N/A | ⚪ | `:78-90` |
| POST/GET/PATCH | `/api/admin/users[/:id]` | إدارة الموظفين | super_admin | … | … | N/A | ⚪ | `:705-766` |

### 4.2 Config & Settings

| Method | Endpoint | Purpose | Auth / Perm | Request | Response | ERP Usage | Status | Source |
|---|---|---|---|---|---|---|---|---|
| GET | `/api/config` | أسعار + عروض + بيانات اتصال | public | — | `{offers[], screenRates, podcastRates, reelsPrice, locationRate, weekendDays, weekendSurcharge, supportWhatsapp, address,…}` | READ (لبناء جدول `svc:` ↔ Item) | ✅ | `:113`, `studioConfig.js:118-130` |
| GET/PUT | `/api/admin/settings/rates` | الأسعار | packages.write | … | … | N/A | ⚪ | `:116-151` |
| GET/PUT | `/api/admin/settings/messages` | صياغة الرسائل | packages.write | … | … | N/A | ⚪ | `:155-178` |
| GET/PUT | `/api/admin/settings/offers` | الخدمات/العروض | packages.write | `{offers:[{id,title,booktype,bookable,halls,price,options[{label,price,cameras}],hidePrice,…}]}` | … | READ (نفس بيانات `/config`) | ⚪ | `:181-226` |
| GET | `/api/health` | صحة الخدمة | public | — | `{ok:true}` | READ (health check للمزامنة) | ✅ | `index.js:34` |

### 4.3 Halls & Blocks

| Method | Endpoint | Purpose | Auth / Perm | Request | Response | ERP Usage | Status | Source |
|---|---|---|---|---|---|---|---|---|
| GET | `/api/halls` | القاعات النشطة | public | — | `[{id,name,price_per_hour,open_minute,close_minute,equipment,images,videos,is_active,has_screen,has_whiteboard}]` | READ (master data → Studio Room/Hall في ERP) | ✅ | `:357-360` |
| PATCH | `/api/halls/:id` | تعديل قاعة | halls.write | أي من الحقول | row | N/A | ⚪ | `:362-375` |
| GET | `/api/halls/:id/availability?date=` | الخانات الحرة | public | query `date=YYYY-MM-DD` | `{hall{…}, date, weekend, weekendSurcharge, slots[{startMinute,endMinute,free,blocked,reason}]}` | N/A | ⚪ | `:377-382` |
| GET | `/api/blocks?hallId&from&to` | الساعات المقفولة | bookings.read | query | `[blocks]` | N/A (اختياري للتقويم) | ⚪ | `:385-394` |
| POST / DELETE | `/api/blocks[/:id]` | إقفال/فتح ساعات | bookings.write | `{hallId,date,startMinute,endMinute,reason}` | row / `{ok}` | N/A | ⚪ | `:396-423` |

### 4.4 Bookings

| Method | Endpoint | Purpose | Auth / Perm | Request | Response | DB affected | Side effects | ERP Usage | Status | Source |
|---|---|---|---|---|---|---|---|---|---|---|
| GET | `/api/bookings?hallId&from&to&status&customerId` | قائمة الحجوزات | bookings.read | query (كلها اختيارية؛ `from/to` على `starts_at`) | `[{...bookings.*, hall_name, package_name}]` **LIMIT 500** مرتَّبة بـ `starts_at` | — | — | **READ (المصدر الرئيسي للمزامنة)** | 🔧 يحتاج: فلتر `updatedSince` على `updated_at`، pagination (cursor أو `limit/offset`)، ترتيب بـ `updated_at`، وإرجاع `photographer_id/created_by` (موجودان ضمن `b.*` فعلاً)، وربما تضمين `payments` | `:569-584` |
| GET | `/api/me/bookings` | حجوزات العميل | auth (customer) | — | `[...]` LIMIT 200 | — | — | N/A | ⚪ | `:586-593` |
| POST | `/api/me/bookings` | العميل يحجز | auth | `{hallId,date,startMinute,endMinute,notes?,sessionType?,bookingType?,screenSize?,cameras?}` | `201 booking` / 409 / 422 | bookings, customer_packages, package_usage | WhatsApp/Telegram, Excel, audit, low-balance alert | N/A | ⚪ | `:471-477` |
| POST | `/api/bookings` | الموظف يحجز | bookings.write | نفس + `{customerId?\|customerName,customerPhone?}` + `pricing?` | `201 booking` | + users (auto-create) | نفسها | N/A (WRITE محتمل مستقبلاً) | ⚪ | `:480-513` |
| POST | `/api/bookings/:id/confirm` | تأكيد العميل | auth (owner) | — | booking | bookings.status | WhatsApp, Excel, audit | N/A | ⚪ | `:516-533` |
| POST | `/api/bookings/:id/pay` | دفعة | payments.write | `{amount>0, method?='cash', settle?}` | booking | bookings.amount_paid/payment_status[/amount_due], **payments (insert)** | audit | N/A (WRITE محتمل) | ⚪ | `:536-554` |
| PATCH | `/api/bookings/:id/amount-due` | تعديل المستحق/إعفاء | payments.write | `{amountDue>=0}` | booking | bookings | audit | N/A | ⚪ | `:557-567` |
| POST | `/api/bookings/:id/cancel` | إلغاء | auth (owner أو staff) | `{note?}` | `{ok}` | bookings, package_usage, customer_packages, payments (refund) | WhatsApp, Excel, audit | N/A | ⚪ | `:595-610` |
| PATCH | `/api/bookings/:id/reschedule` | نقل | auth (owner أو staff) | `{date,startMinute,endMinute}` | booking | bookings | Excel, audit | N/A | ⚪ | `:612-628` |
| POST | `/api/bookings/:id/apply-package` | تطبيق باقة على حجز قائم | bookings.write | `{packageId}` | `{ok,deducted,amountDue}` | customer_packages, bookings, package_usage | audit | N/A | ⚪ | `:632-663` |
| POST | `/api/bookings/:id/complete` | إتمام + دفعة | bookings.write | `{amountPaid?,method?}` | booking | bookings.status='completed', payments | WhatsApp, Excel, audit | N/A | ⚠️ (لا يتحقق من الحالة السابقة) | `:666-689` |
| GET | `/api/bookings/:id/invoice` | PDF | auth (owner/staff) | — | `application/pdf` | — | — | N/A | ⚪ | `:691-702` |
| PATCH | `/api/bookings/:id/photographer` | تعيين المصوّر | bookings.write أو payments.write | `{photographerId\|null}` | `{id,photographer_id}` | bookings | audit | N/A | ⚪ | `:1089-1103` |

### 4.5 Packages

| Method | Endpoint | Purpose | Auth / Perm | Request | Response | ERP Usage | Status | Source |
|---|---|---|---|---|---|---|---|---|
| GET | `/api/package-templates` | الكتالوج النشط | public | — | `[{id,name,hours,price,validity_days,category,is_active,created_at}]` | READ (master data → Item/Package Type) | ✅ | `:778-781` |
| POST / PATCH | `/api/package-templates[/:id]` | إدارة الكتالوج | packages.write | … | row | N/A | ⚪ | `:783-793, 238-263` |
| POST | `/api/customers/:id/packages` | بيع باقة | packages.assign | `{templateId?, name?,hours?,price?,validityDays?, paidAmount?}` | `201 customer_package` | N/A | ⚪ | `:797-822` |
| POST | `/api/me/packages` | العميل يفعّل باقة (غير مدفوعة) | customer | `{templateId}` | `201` / 409 | N/A | ⚪ | `:882-901` |
| GET | `/api/me/packages` | باقات العميل | auth | — | `[customer_packages]` | N/A | ⚪ | `:903-907` |
| GET | `/api/customers/:id/packages` | باقات عميل مع الـ ledger | packages.read | — | `[{...cp, category, paid_total, payments[{amount,method,created_at}], usage[{id,package_id,booking_id,hours,reason,created_at}]}]` | **READ (الباقات + الاستهلاك + دفعات الباقة)** | 🔧 لكل عميل على حدة (N+1)؛ يحتاج endpoint مجمَّع `GET /api/customer-packages?updatedSince` + `GET /api/package-usage?since`؛ **`payments[]` لا تُرجع `id`** → لا يمكن منع التكرار | `:909-919` |
| PATCH | `/api/customer-packages/:id` | تعديل باقة (رصيد/سعر/حالة) | packages.write | `{hoursRemaining?,hoursTotal?,price?,name?,paymentStatus?}` | row | N/A | ⚠️ (يغيّر `hours_remaining` بلا ledger ولا `updated_at`) | `:825-845` |
| POST | `/api/customer-packages/:id/payment` | دفعة على باقة | payments.write | `{amount>0, method?}` | `{ok,paid,remaining}` | N/A | ⚪ | `:848-861` |
| DELETE | `/api/customer-packages/:id` | حذف باقة | packages.write | — | `{ok}` | N/A | ⚠️ (حذف فعلي يمسح الـ ledger) | `:865-878` |

### 4.6 Customers

| Method | Endpoint | Purpose | Auth / Perm | Request | Response | ERP Usage | Status | Source |
|---|---|---|---|---|---|---|---|---|
| GET | `/api/customers?q=` | قائمة العملاء مع إجماليات | customers.read | `q` (name/phone LIKE) | `[{id,name,phone,email,notes,created_at,total_hours_booked,total_spent,outstanding,hours_remaining,reels_remaining}]` **LIMIT 200** | **READ (master data → Customer)** | 🔧 حد 200 بلا pagination؛ لا `updated_at` على `users`؛ لا `address/is_active` في الإخراج | `:922-938` |
| GET | `/api/admin/customers/search?q=` | autocomplete | bookings.read | `q` ≥ 2 | `[{id,name,phone,address,remaining_hours,remaining_reels}]` LIMIT 8 | N/A | ⚪ | `:330-354` |
| POST | `/api/customers` | إنشاء عميل (+باقة ابتدائية) | customers.write | `{name,phone,notes?,templateId?\|packageName,hours,price, paidAmount?}` | `201 {id,name,phone}` | N/A | ⚪ | `:979-1015` |
| PATCH | `/api/customers/:id` | تعديل | customers.write | `{name?,phone?,notes?}` | row | N/A | ⚪ | `:941-960` |
| DELETE | `/api/customers/:id` | حذف (إن لا حجوزات/باقات) | customers.write | — | `{ok}` | N/A | ⚪ | `:964-975` |
| POST | `/api/admin/customers/import` | استيراد من شيت | packages.assign | `{rows:[{name,phone,type,hours,price,paid,remaining,startDate,notes}]}` | `{created,packages,skipped,errors[]}` | N/A | ⚪ | `:266-327` |

### 4.7 Reports, Photographers, Weekly account

| Method | Endpoint | Purpose | Auth / Perm | Request | Response | ERP Usage | Status | Source |
|---|---|---|---|---|---|---|---|---|
| GET | `/api/reports/revenue?granularity=daily\|monthly` | إيراد من `payments` | reports.read | — | `[{period, revenue}]` (90 صف) | READ (مطابقة إجمالية) | ✅ | `:1018-1024` |
| GET | `/api/reports/utilization?from&to` | إشغال القاعات | reports.read | dates | `[{id,name,booked_hours,booking_count,open_hours,utilization_pct}]` | READ (اختياري) | ✅ | `:1026-1038` |
| GET | `/api/reports/outstanding` | مستحقات | reports.read | — | `[{id,customer_name,customer_phone,hall_name,starts_at,balance}]` 200 | READ (مطابقة) | ✅ | `:1040-1048` |
| GET | `/api/reports/unpaid-past` | جلسات انتهت ولم تُسوَّ | payments.read | — | `[{id,…,price_pending,type_label}]` 200 | READ (مطابقة) | ✅ | `:1052-1062` |
| GET | `/api/reports/week?start=YYYY-MM-DD` | حجوزات الأسبوع + القفل | reports.read | `start` (سبت) | `{start, bookings[], closing{week_start,data,closed_at,closed_by_name}\|null, lastPcts, lastBase}` | **READ (نسب المصورين → مستحقات موظفين في ERP)** | ✅ | `:1146-1157` |
| PUT | `/api/reports/week/:start/close` | قفل الأسبوع | payments.write | `{base:'paid'\|'price', pcts{[photographerId]:{[bucket]:pct}}, notes}` | `{ok,data}` | N/A | ⚪ | `:1160-1206` |
| GET/POST/PATCH | `/api/photographers[/:id]` | المصورون | bookings.read / payments.write | … | `[{id,name,is_active}]` | READ (→ Employee mapping) | ✅ | `:1065-1087` |

### 4.8 Payments — **لا يوجد endpoint مستقل**

| ما هو موجود | ما هو غير موجود |
|---|---|
| دفعات الحجز تُدرج عبر `/bookings/:id/pay`, `/bookings/:id/complete`, والاسترداد داخل `cancelBooking` | ❌ `GET /api/payments` (قائمة الدفعات مع `id, booking_id, package_id, amount, method, recorded_by, created_at`) |
| دفعات الباقة عبر `/customers/:id/packages`, `/customer-packages/:id/payment`, `/customers`, `/admin/customers/import` | ❌ أي طريقة لقراءة دفعة بعينها بمعرّفها |
| `GET /api/customers/:id/packages` يُرجع `payments[]` **بدون `id`** | ❌ قراءة `payments` للحجوزات إلا عبر `GET /api/admin/export` (كل الجداول دفعة واحدة) |

→ **هذه أكبر فجوة في الـ API للتكامل المالي** (انظر §5 M-02).

### 4.9 Notifications, Excel, Export, Cron

| Method | Endpoint | Purpose | Auth / Perm | ERP Usage | Status | Source |
|---|---|---|---|---|---|---|
| GET | `/api/me/notifications`, `/api/notifications/admin` | رسائل | auth / notifications.read | N/A | ⚪ | `:1209-1224` |
| PATCH | `/api/notifications/:id/sent` | تعليم كمرسَل | notifications.read | N/A | ⚪ | `:1228-1235` |
| GET | `/api/excel/export` | xlsx كامل | bookings.export | بديل يدوي | ⚪ | `:770-775` |
| GET | `/api/admin/export` | JSON لكل الجداول | super_admin/manager | **READ (initial import مرة واحدة)** | ⚠️ يُسرِّب `password_hash`؛ يحتاج دور أعلى؛ غير مناسب للتكرار | `:94-109` |
| POST | `/api/internal/cron/reminders`, `/api/internal/cron/package-alerts` | cron | bookings.write | N/A | ⚪ | `:1238-1243` |

### 4.10 ملاحظات أمنية على الـ API الحالي (ذات صلة بالتكامل)

1. **JWT بسر افتراضي** إن لم يُضبط `JWT_SECRET` (`db.js:6`) — يجب التأكد أنه مضبوط في الإنتاج (**Q-X2**).
2. **لا يوجد دور قراءة-فقط مع صلاحيات تقارير**: `viewer` يرى `bookings.read, halls.read` فقط (لا `packages.read`, لا `reports.read`, لا `customers.read`)؛ `accountant` يملك `payments.write`. حساب الخدمة للـ ERP يحتاج دوراً جديداً `integration` = `{bookings.read, halls.read, customers.read, packages.read, payments.read, reports.read}` بلا أي write.
3. **التوكن 7 أيام بلا تجديد** → المزامنة ستنقطع أسبوعياً ما لم يُعاد الدخول بكلمة السر (تخزين كلمة سر في ERP) أو يُضاف API key طويل الأمد.
4. **`GET /api/admin/export` يُخرج `users.password_hash`** لكل المستخدمين.
5. **لا rate limit** إلا على `/auth/*` و`/me/password`.
6. **CORS غير مضبوط** (لا `cors` middleware) → الطلبات من ERP backend (server-to-server) لا تتأثر، لكن لا يوجد allowlist للـ origins أيضاً.
7. **Security headers** موجودة فقط في النسخة الطائشة `xstudio-platform/index.js:13-21` وليس في `backend/src/index.js`.
8. **HTTPS**: يُفترض إنهاؤه عند Railway (`trust proxy`, `index.js:12`); لا HSTS.
9. **رسائل الخطأ عربية بشرية** وليست أكواداً → ERP يجب أن يعتمد على HTTP status فقط.

---

## 5. Missing or Incomplete Endpoints (مقترَحة — **NOT YET IMPLEMENTED**)

> كل ما في هذا القسم **مقترح** ولم يُنفَّذ. المالك: **XStudio Backend** إلا إذا ذُكر غير ذلك. كل endpoint جديد يجب أن: يتطلب دور `integration` (أو صلاحية `integration.read`), يدعم `limit` (افتراضي 200، أقصى 1000) و`cursor` (مبني على `(updated_at, id)` أو `(created_at, id)`), ويُرجع `{ data: [...], nextCursor: string|null, serverTime: ISO }`.

### M-00 — دور `integration` + API key طويل الأمد (أساس لكل ما يلي)

| البند | التفاصيل |
|---|---|
| تغيير | في `backend/src/middleware/auth.js:7-27` إضافة `integration: ["bookings.read","halls.read","customers.read","packages.read","payments.read","reports.read","integration.read"]`؛ إضافة القيمة `integration` (و`viewer` المفقود) إلى enum `user_role` عبر `ensureSchema()` في `index.js:48-63` بـ `ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'integration'`. |
| Auth | بديلان: (أ) حساب `integration` عادي + ERP يجدّد التوكن بـ `/auth/login` كل < 7 أيام (الأبسط، يتطلب تخزين كلمة السر مشفَّرة في ERP `Password` field)؛ (ب) **موصى به**: جدول `api_keys (id, user_id, key_hash, label, last_used_at, revoked_at)` + header `X-Api-Key` يُقبل في `authRequired`. |
| Error | 401/403 كالمعتاد. |
| Owner | XStudio Backend. |

### M-01 — `GET /api/integration/bookings?updatedSince=<ISO>&cursor=&limit=`

| البند | التفاصيل |
|---|---|
| الغرض | المصدر الرئيسي للمزامنة التزايدية (incremental). |
| Query | `updatedSince` (ISO timestamptz، شامل `>=`)، `cursor` (opaque: base64 of `updated_at|id`)، `limit`، اختياري `status`, `hallId`, `from`, `to`. |
| Response | `{ data: [ { id, hall_id, hall_name, customer_id, customer_name, customer_phone, starts_at, ends_at, hours, booking_type, booking_type_label, screen_size, cameras, status, price_total, price_pending, deposit_due, amount_due, amount_paid, payment_status, package_id, hours_deducted, photographer_id, photographer_name, cancelled_by, cancel_note, notes, created_by, created_at, updated_at, payments: [{id, amount, method, recorded_by, created_at}], package_usage: [{id, package_id, hours, reason, created_at}] } ], nextCursor, serverTime }` |
| Ordering | `ORDER BY updated_at, id` (ثابت للـ cursor). |
| Validation | `updatedSince` ISO صالح؛ `limit` 1..1000. |
| Models | `bookings` ⟕ `halls` ⟕ `photographers` + `payments` + `package_usage`. |
| Code changes | `routes.js` route جديد (أو ملف `routes/integration.js` جديد)؛ index موجود على `bookings(hall_id, starts_at)` فقط → إضافة `CREATE INDEX IF NOT EXISTS bookings_updated_idx ON bookings(updated_at, id)` في `ensureSchema()`. |
| ملاحظة | `updated_at` **لا يتغيّر** عند إدراج `payments` أو `package_usage` لحجز (الـ trigger على `bookings` فقط). لكن كل دفعة حجز تمرّ بـ `UPDATE bookings SET amount_paid…` فتُحدِّث `updated_at` ضمنياً ✅. `apply-package` يحدّث `bookings` ✅. تعيين المصوّر يحدّث `bookings` ✅. |

### M-02 — `GET /api/integration/payments?since=<ISO>&cursor=&limit=`

| البند | التفاصيل |
|---|---|
| الغرض | قراءة سجل الدفعات (append-only) بمعرّفاته — **ضروري لأي Payment Entry في ERP**. |
| Query | `since` على `created_at` (الدفعات لا تُعدَّل أبداً)؛ `cursor`, `limit`. |
| Response | `{ data: [{ id, booking_id, package_id, customer_id (via join), customer_name, amount, method, recorded_by, recorded_by_name, created_at }], nextCursor, serverTime }` |
| Models | `payments` ⟕ `bookings`/`customer_packages` ⟕ `users`. |
| Code changes | route + `CREATE INDEX IF NOT EXISTS payments_created_idx ON payments(created_at, id)`. |

### M-03 — `GET /api/integration/customer-packages?updatedSince=&cursor=&limit=` + `GET /api/integration/package-usage?since=`

| البند | التفاصيل |
|---|---|
| المشكلة | `customer_packages` **لا يملك `updated_at`**؛ `PATCH /customer-packages/:id` يغيّر `hours_remaining/price/payment_status` بصمت. |
| تغيير DB | في `ensureSchema()`: `ALTER TABLE customer_packages ADD COLUMN IF NOT EXISTS updated_at timestamptz NOT NULL DEFAULT now()` + trigger `set_updated_at` (الدالة موجودة `schema.sql:168-170`). نفس الشيء لـ `users` (M-04). |
| Response (packages) | `{ data: [{ id, customer_id, template_id, template_category, name, hours_total, hours_remaining, unit ('hour'\|'reel' مستنتَج من category), price, payment_status, purchased_at, expires_at, updated_at, deleted_at? }], … }` |
| Response (usage) | `{ data: [{ id, package_id, booking_id, hours, reason, created_at }], … }` — `package_usage` append-only فيكفي `since` على `created_at`. |
| **Soft delete** | `DELETE /customer-packages/:id` (`routes.js:865-878`) يحذف فعلياً ويمسح الـ ledger. **مقترح:** تحويله إلى soft delete (`deleted_at`) أو على الأقل تسجيل سطر `package_usage reason='deleted'` ← **قرار للمطوّر (Q-X5)**. |

### M-04 — `GET /api/integration/customers?updatedSince=&cursor=&limit=`

| البند | التفاصيل |
|---|---|
| Response | `{ data: [{ id, name, phone, email, address, notes, is_active, created_at, updated_at }], … }` — بدون أي إجماليات ثقيلة. يحتاج `users.updated_at` (M-03). |
| Privacy | لا `password_hash` أبداً. |

### M-05 — `GET /api/integration/week-closings?since=` (و/أو تضمين `photographers`)

| البند | التفاصيل |
|---|---|
| الغرض | مستحقات المصورين الأسبوعية → ERP (Journal Entry/Expense Claim لاحقاً). |
| Response | `{ data: [{ week_start, closed_at, closed_by, data: { base, pcts, lines[{photographer_id, photographer_name, bucket, count, amount, pct, cut}], totals, total_cut, notes } }] }` |
| ملاحظة | `week_closings` تُستبدل بالكامل عند إعادة القفل (`ON CONFLICT DO UPDATE`, `routes.js:1201-1203`) → ERP يحتفظ بنسخة بـ `closed_at` ويعتبر أي `closed_at` أحدث تعديلاً (version). |

### M-06 — `GET /api/integration/audit-logs?sinceId=<bigserial>&limit=` (اختياري — change feed)

| البند | التفاصيل |
|---|---|
| الغرض | بديل قوي للكشف عن أي تغيير (خصوصاً `package.update`, `package.delete`, `booking.adjust_due`, `week.close`) لأن `audit_logs.id` متسلسل (`bigserial`) → cursor مثالي. |
| Response | `{ data: [{ id, user_id, action, entity, entity_id, meta, created_at }], nextId }` |
| تحذير | `meta` قد يحوي بيانات شخصية (أسماء/هواتف) → مقبول داخل التكامل، لا يُعرض خارج ERP. |

### M-07 — Webhook صادر (اختياري، Phase 2) — `POST <ERP_URL>/api/method/imed.integrations.xstudio.webhook`

| البند | التفاصيل |
|---|---|
| تغيير XStudio | دالة `emitWebhook(event, payload)` تُستدعى بعد `COMMIT` في `handleCreateBooking`, `confirm`, `pay`, `amount-due`, `cancel`, `reschedule`, `apply-package`, `complete`, `photographer`, `customers/:id/packages`, `customer-packages/:id[/payment]`, `week/:start/close`. تُرسل `{ event, occurredAt, entity, entityId, data }` مع header `X-XStudio-Signature: sha256=HMAC(secret, body)` و`X-XStudio-Delivery: <uuid>`. |
| جدول | `webhook_deliveries (id, event, payload, status, attempts, last_error, next_attempt_at)` + retry خلفي (مثل timers الموجودة في `index.js`). |
| ERP side | whitelisted method يتحقق من HMAC + timestamp ± 5 دقائق، يخزّن في Integration Import Log، ويُطلق **نفس** مسار المعالجة المستخدم في الـ polling (الـ webhook مجرد مُسرِّع، والـ polling يبقى شبكة الأمان). |
| Owner | Both. |

### M-08 — تصحيحات سلوك (ليست endpoints) مطلوبة لسلامة البيانات

| ID | التغيير | السبب | Source |
|---|---|---|---|
| F-01 | `POST /bookings/:id/complete` يرفض إذا `status='cancelled'` (ويفضَّل أيضاً إذا `completed` بالفعل بدون `amountPaid`) | يمكن حالياً إكمال حجز ملغي وتسجيل دفعة عليه | `routes.js:666-673` |
| F-02 | `PATCH /customer-packages/:id` عند تغيير `hoursRemaining` يكتب سطر `package_usage reason='manual_adjust'` بالفرق | الحفاظ على الـ ledger كمصدر حقيقة للرصيد | `routes.js:825-845` |
| F-03 | `POST /bookings/:id/pay` مع `settle=true` يكتب سطر توضيحي (مثلاً `payments` بـ `method='discount'` و`amount` سالب؟ أو عمود `discount_amount` على `bookings`) | حالياً الخصم ضمني فقط ولا يمكن لـ ERP تمييزه عن تعديل سعر | `routes.js:545-549` |
| F-04 | تخزين `people`/`per_person` من `pricing.mode='per_person'` في عمودين على `bookings` | حالياً في `audit_logs.meta` فقط؛ ERP يحتاج عدد الحضور لتقارير HAL | `bookingService.js:217-219`, `routes.js:463-465` |
| F-05 | إضافة `viewer` و`integration` إلى enum `user_role` | إنشاء المستخدم يفشل على DB نظيفة | `schema.sql:12` |
| F-06 | `GET /api/admin/export` يستثني `password_hash` | تسريب | `routes.js:98-104` |

### 5.1 API Documentation

- **لا يوجد OpenAPI/Swagger.** `docs/api.md` يدوي وقديم (انظر §2.3).
- **توصية:** إضافة `docs/openapi.yaml` يدوي للـ endpoints الـ `/api/integration/*` فقط (العقد بين النظامين)، مع contract tests في `backend/test/integration-api.test.js` تتحقق أن شكل الاستجابة يطابق الـ schema (مكتبة `ajv`). الـ endpoints الداخلية الأخرى تبقى موثَّقة في `api.md`.
- ERP يحتفظ بنسخة من `openapi.yaml` في `docs/integrations/xstudio/` ويُشغِّل contract test ضدّ environment الاختبار.

---

## 6. XStudio vs IMED ERP — Feature Gap Analysis (مصفوفة الفجوات)

### 6.1 ما يوجد في ERP اليوم (ملخّص من الكود)

> المسارات نسبية إلى `apps/imed_erp/imed_erp/` (مختصرة `APP/`).

| المكوّن | الموجود | المصدر |
|---|---|---|
| **Booking** DocType | واحد للاستوديو والقاعات؛ `resource` Link [Booking Resource]، `customer` Link [Customer]، `booking_date` + `from_time/to_time` (نفس اليوم فقط)، `hours`، **status** = `Tentative | Confirmed with Deposit | Completed | Cancelled | No Show`، أقسام Hall (`rental_model` = `Fixed Rent | Revenue Share`, `activity`, `responsible_name/phone`, `attendees`, `admission_price`, `collected_amount`, `lecturer` Link [**Supplier**], `lecturer_share_percent`), `hour_package` Link [Studio Hour Package], `package`, `extras`, تسعير (`rate`, `base_amount`, `total_amount`, `paid_amount`, `outstanding_amount`), روابط `sales_invoice`, `journal_entry`, **قسم Source**: `source` (`Manual|Imported`), `source_system`, `external_id`, `import_key` (**unique** = `"{source_system}:{external_id}"`) | `APP/imederp/doctype/booking/booking.json`, `booking.py:33-37,124-145` |
| **Booking Resource** | `resource_type` = `Hall | Studio Service`, `cost_center`, `item`, `capacity`, `equipment` | `booking_resource.json` |
| **Studio Hour Package** (submittable) | `customer` ("Teacher"), `resource` (Studio Service), `purchase_date`, `hours_purchased`, `price`, `status` = `Draft|Active|Used Up|Cancelled`, `hours_used`, `hours_remaining`, child **Usage** ledger (`booking`, `hours` ±, `balance`, `reason`), `sales_invoice`. **لا external_id، لا expiry** | `studio_hour_package.json`, `studio_hour_package.py` |
| **Booking Package / Booking Extra** | باقات سعرية (Once/Per Hour) وإضافات (مايك/إضاءة) | `booking_package.json`, `booking_extra.json` |
| **Customer** | الطرف الوحيد (مدرّس/طالب/طبيب)؛ `custom_phone_key` unique مُطبَّع عبر `normalize_phone()`؛ **لا external_id** | `APP/imederp/customers.py:41-109` |
| **المالية** | `booking_accounts.py`: Payment Entry عبر `record_payment()` (idempotent بـ `custom_booking_request`)، Sales Invoice عند Completed، Journal Entry للـ Revenue Share (Dr خزينة سنتر / Cr إيراد القاعات / Cr مستحقات للمحاضرين)؛ مركز تكلفة `استوديو X`، خزينة `خزينة X Studio`، Mode of Payment `نقدي — استوديو X`, `InstaPay`, `Vodafone Cash`؛ Items `STU-*` | `booking_accounts.py:34-38,238-326,427-526`, `setup/setup_booking_prices.py` |
| **الحجوزات المستوردة** | `booking_import.import_bookings(source_system, rows)` موجود **وغير موصول** (لا scheduler، لا API، لا Import Log)؛ الحجز المستورد: read-only، لا تسعير، لا فاتورة/دفعة/باقة، `record_payment` يرفضه، `check_overlap` يُطبَّق | `booking_import.py:1-103`, `booking.py:139-143`, `booking_accounts.py:250-251` |
| **Integration Import Log** | `source_system` Select = `ba_plus | library_pos | booking`؛ `status` = `Completed | Completed with Errors | Failed`؛ عدّادات `rows_read, inserted, records_created, skipped, changed, failed`; child Errors (`kind` = `Failed | Changed in Source`)؛ class `ImportRun`؛ تقرير **Integration Status** | `integration_import_log.{json,py}`, `report/integration_status/` |
| **الخزنة** | Treasury Close يومي لكل خزنة، Weekly Cash Reconciliation، Cash Handover، Cash Discrepancy؛ `cash_balance` يمنع الرصيد السالب | `doctype/treasury_close/`, `treasuries.py`, `cash_balance.py` |
| **Scheduler / outbound HTTP / webhooks / settings credentials** | **لا شيء** (scheduler فقط `recurring_expense`, `doctor_accrual`) | `hooks.py:546-552` |

### 6.2 مصفوفة الفجوات

| XStudio Feature | Exists in XStudio? | Exists in ERP? | Compatible? | Gap | Required Action | Priority |
|---|---|---|---|---|---|---|
| Studio booking (session/smartboard/podcast/reels/location/svc) | ✅ `bookings.booking_type` | ✅ `Booking` + `Booking Resource (Studio Service)` | 🟡 | ERP يحتاج **Resource لكل نوع حجز XStudio** أو لكل قاعة؟ XStudio يحجز **قاعة** (`hall_id`) بنوع خدمة؛ ERP يحجز **Resource** (خدمة أو قاعة). المورد المحجوز فعلياً في XStudio = القاعة (+ كاميرات مشتركة) | **Introduce data mapping**: جدول `XStudio Resource Map` (hall_id + booking_type → Booking Resource). توصية: Resource لكل **قاعة XStudio** (6 موارد Studio Service) لأن قيد التعارض في XStudio على القاعة؛ نوع الخدمة يُحفظ في حقل جديد `xstudio_booking_type` وItem للتسعير | P0 |
| Multi-day / same-day constraint | XStudio يسمح بـ `starts_at/ends_at` أي timestamps (الواجهة تقيّدها بيوم واحد) | ERP `check_times`: نفس اليوم فقط (`booking.py:175-186`) | 🟡 | حجز يعبر منتصف الليل (close_minute=1440 يسمح حتى 24:00 بالضبط) | **Extend ERP**: الاستيراد يرفض/يسجّل كـ Failed أي حجز `ends_at` > نهاية اليوم؛ ساعة 24:00 تُحوَّل إلى `23:59:59`? → **قرار** (Q-B3). الأبسط: تخزين `to_time = 24:00:00` غير مدعوم في Frappe Time → استعمال `23:59:59` مع حفظ الأصل في `xstudio_ends_at` | P1 |
| Booking statuses | `pending, confirmed, completed, cancelled` | `Tentative, Confirmed with Deposit, Completed, Cancelled, No Show` | ❌ **دلالة مختلفة** | ERP: `Confirmed with Deposit` **يتطلب `paid_amount > 0`** (`booking.py:293`)؛ XStudio: `confirmed` لا علاقة له بالدفع. XStudio لا يملك `No Show` | **Introduce data mapping + Extend ERP**: `pending→Tentative`; `confirmed→Tentative` إذا `amount_paid=0` و`Confirmed with Deposit` إذا `>0`; `completed→Completed`; `cancelled→Cancelled` (reason = `cancel_note` أو "Cancelled in XStudio by {cancelled_by}"). حفظ الحالة الأصلية في `xstudio_status`. **ملاحظة**: ERP يمنع `Completed` قبل وقت البدء (`booking.py:296`) — XStudio لا يمنع → الاستيراد يسجّل Failed للحالة الشاذة | P0 |
| Rescheduling | ✅ نفس المدة فقط | ✅ تعديل الوقت (Manual) | 🟡 | **ERP يرفض تعديل الحجز المستورد نهائياً** (`booking.py:139-143`)، والمستورد يُسجَّل "Changed in Source" ولا يُحدَّث (`booking_import.py:43-48`) | **Extend ERP** (قرار INT-01 معلَّق): السماح للمستورد بالتحديث من المصدر فقط عبر flag `from_import` + فحص `source_updated_at` أحدث. التحديث يعيد `check_overlap` | P0 |
| Cancellation + package refund | ✅ ledger `cancel_refund` | ✅ `draw()` يُعيد الساعات (`studio_hour_package.py:135-146`) **للحجز اليدوي فقط**؛ المستورد لا يستعمل باقات (`booking.py:102-103`) | ❌ | الباقات المستوردة لا تُستهلك في ERP حالياً | **Extend ERP**: مسار استهلاك مستورد يأخذ `package_usage` من XStudio كما هو (mirror) بدلاً من إعادة حسابه | P0 |
| Completion → payment | `complete` يضيف دفعة اختيارية ولا يتحقق من الحالة | ERP `Completed` → Sales Invoice (Manual فقط) | ❌ | ERP يفترض الدفع عبر Payment Entry؛ XStudio يُسجِّل الدفع كسطر `payments` | **Introduce mapping + Business decision** (§12): هل تُنشأ PE/SI للحجوزات المستوردة؟ | P0 |
| Walk-in customers / auto-create by phone | ✅ ينشئ `users` | ❌ `booking_import` **يرفض** عميلاً غير موجود (`booking_import.py:12-13`) | ❌ | كل عميل جديد في XStudio يُفشِل حجوزاته | **Extend ERP** + **Business decision** (Q-B1): إنشاء Customer تلقائياً من XStudio (مجموعة `مدرّس`؟) كما يفعل BA Plus importer (`app_import.py:238-249`) | P0 |
| Customer identity | `users.phone` UNIQUE (قد يكون `no-phone-xxxx` placeholder من الاستيراد `routes.js:285`) | `custom_phone_key` unique مطبَّع | 🟡 | هواتف placeholder؛ هواتف بصيغ مختلفة (`+20…`, `01…`, `20…`) | **Reuse ERP** `normalize_phone()` + **إضافة `xstudio_customer_id` على Customer** كمفتاح أساسي للمطابقة (الهاتف ثانوي) | P0 |
| Prepaid hour packages | ✅ `customer_packages` + `package_usage` | ✅ `Studio Hour Package` + Usage child | 🟡 **متوافقان مفهومياً** | ERP: مرتبط بـ `resource` واحد، لا `expires_at`، لا `payment_status`, لا `template`, لا external id؛ وحدة الريل غير موجودة؛ Usage child read-only يُكتب فقط عبر `record()` | **Extend ERP**: حقول `source/source_system/external_id/import_key`, `expires_at`, `xstudio_payment_status`, `unit (Hour/Reel)`, `template_name/category`; مسار `import_usage()` يكتب Usage rows من ledger XStudio (مع `external_id` لكل سطر) | P0 |
| Package purchase payment | ✅ `payments.package_id` | ✅ `make_invoice()` فاتورة بسعر الباقة + PE يدوي | 🟡 | قرار محاسبي: إيراد عند البيع أم مؤجَّل (`v1.3-amendments.md:93`) | **Business decision** (Q-B4) ثم Extend | P1 |
| Package manual edit / delete | ✅ بلا ledger / حذف فعلي | ERP يمنع تعديل الرصيد يدوياً (كل تغيير عبر Usage) | ❌ | تغييرات صامتة في XStudio لا تُكتشف إلا بالمقارنة الكاملة | **Modify XStudio** (F-02, soft delete) + **Reconciliation** في ERP تكتشف فرق `hours_remaining` | P1 |
| Reels bundles (unit = reel) | ✅ | ❌ ERP لديه Items `STU-REEL-*` كـ Booking Package `hours=0` فقط | ❌ | رصيد الريلز سيُفسَّر كساعات | **Extend ERP**: `unit` على Studio Hour Package (أو DocType منفصل `Studio Credit Package`) | P1 |
| Pricing (server-side, rates, surcharge, custom price, per-person, pending) | ✅ | ✅ `booking_pricing.py` (Item Price) — **لا يُطبَّق على المستورد** (`check_amounts` فقط) | 🟡 | الأسعار قد تختلف بين النظامين (مثلاً podcast 1cam: XStudio 800 / ERP `STU-PODCAST-1CAM` 1250) | **Keep in XStudio** كمصدر للسعر؛ ERP يستورد `price_total/amount_due/amount_paid` كما هي (`total_amount=amount_due`? → انظر §8) + تقرير فرق الأسعار | P0 |
| `price_pending` (سعر معلَّق) | ✅ | ❌ | ❌ | حجز بـ 0 سيبدو مجانياً | **Extend ERP**: حقل `price_pending` Check؛ يُستثنى من الإيراد ومن المطابقة حتى يُحدَّد | P1 |
| Deposit 50% (`deposit_due`) | ✅ محسوب | `Confirmed with Deposit` + `record_payment` "deposit" | 🟡 | ERP يعتبر أي دفعة قبل الفاتورة عربوناً؛ لا حقل "عربون مستحق" | **Extend ERP**: حقل `deposit_due` للعرض فقط | P2 |
| Discounts (`settle`), `amount-due` adjustments | ✅ ضمنية | ERP: `pricing_note`؛ لا خصم صريح للمستورد | ❌ | الفرق `price_total − amount_due` هو خصم ضمني أو تغطية باقة | **Introduce mapping**: `discount_amount = price_total − amount_due − (hours_deducted × rate)` محسوب في ERP + F-03 في XStudio | P1 |
| Hall rental (`hall_rental`, `location_rental`) | ✅ إيجار قاعة تصوير | ✅ `Fixed Rent` على Resource من نوع Hall | 🟡 **خلط مفاهيم** | هذه ليست "قاعات Imed" (مركز تكلفة `قاعات Imed`) بل قاعات الاستوديو (مركز `استوديو X`) | **Introduce mapping**: `hall_rental/location_rental` → Resource Studio Service (قاعة X) بمركز تكلفة `استوديو X`؛ **لا يُستعمل** `resource_type=Hall` | P0 |
| Revenue Share (lecturer) | ❌ | ✅ JE لمستحقات المحاضرين | — | **لا يوجد ما يُزامَن**: قاعات Imed للمحاضرات لا تُدار في XStudio | **Keep in ERP only** (manual). **Business decision (Q-B6)**: هل تُنقل حجوزات قاعات Imed إلى XStudio لاحقاً؟ | — |
| Attendees / per-person pricing | 🟡 غير مخزَّن | ✅ `attendees` (Revenue Share فقط) | ❌ | | **Modify XStudio** (F-04) ثم mapping إلى `attendees` | P2 |
| Photographers & weekly cut | ✅ `photographers`, `week_closings` | ❌ لا مكافئ (الأقرب: Expense / Journal Entry يدوي؛ Employee غير مستخدم) | ❌ **ميزة ناقصة في ERP** | مستحقات المصورين = مصروف الاستوديو | **Extend ERP** (جديد): DocType `Studio Week Closing` (mirror) + قرار محاسبي للترحيل (Q-B7) | P1 |
| Blocks | ✅ | ❌ | — | غير مالي | **Keep in XStudio** (اختياري: عرض في تقويم ERP) | P3 |
| Notifications WhatsApp/Telegram | ✅ | skeleton فقط (`notification_service.py`) | — | | **Keep in XStudio** | — |
| Audit log | ✅ `audit_logs` | ✅ `track_changes` + Version | — | | **Reuse** (M-06 اختياري كـ change feed) | P2 |
| Reports (revenue/utilization/outstanding) | ✅ | Hall Bookings report فقط؛ لا تقرير استوديو | 🟡 | | **Extend ERP**: تقرير "Studio Bookings" + تقرير مطابقة (§14) | P1 |
| Treasury / cash boxes | ❌ (لا مفهوم خزنة؛ `method` فقط) | ✅ Treasury Close يومي | ❌ | دفعات XStudio لا تعرف في أي خزنة | **Introduce mapping**: `method` → Mode of Payment (`cash→نقدي — استوديو X`, `instapay→InstaPay`, `transfer→?`, `other→?`) **Business decision (Q-B5)** | P0 |
| Overlap prevention | ✅ DB EXCLUDE | ✅ `check_overlap` على Resource+date | 🟡 | إن وُجدت حجوزات يدوية في ERP على نفس Resource ستتعارض مع المستوردة → ERP يرفض الاستيراد ("Already Booked") | **Policy**: موارد XStudio **لا تُحجز يدوياً في ERP** (Resource flag `managed_by = XStudio` يمنع Manual) | P1 |
| Opening hours | ✅ لكل قاعة | STU-15: لا ساعات ثابتة | 🟡 | لا أثر على التكامل (ERP لا يتحقق من ساعات) | لا شيء؛ توثيق فقط | — |
| Multi-tenant / business isolation | ❌ | ✅ User Permission على Cost Center | — | المستخدم التكاملي يحتاج صلاحية `استوديو X` | **Extend ERP**: مستخدم `integration@xstudio` بدور جديد `Integration Runner` | P0 |
| Historical import | ✅ `GET /api/admin/export` أو `GET /bookings?from&to` | ✅ idempotent بالـ `import_key` | 🟡 | 500 صف/طلب؛ لا pagination | **Modify XStudio** (M-01) أو تصدير JSON لمرة واحدة | P0 |
| Incremental sync (`updated_at`) | `bookings.updated_at` ✅؛ باقي الجداول ❌ | ERP لا يملك `source_updated_at` | ❌ | | **Both**: M-01..M-04 + حقول `source_updated_at`, `last_synced_at` في ERP | P0 |
| Webhooks | ❌ | ❌ | — | | Phase 2 (M-07) | P2 |

### 6.3 تصنيف الفجوات (حسب الطلب)

1. **موجود في النظامين**: الحجز بالساعة، منع التعارض، الباقات المسبقة + ledger، الإلغاء مع إعادة الساعات، العملاء بالهاتف، سجل التغييرات، إيجار ثابت.
2. **مُنفَّذ بشكل مختلف**: الحالات (4 vs 5 بدلالة دفع مختلفة)، الكيان المحجوز (قاعة vs Resource خدمة)، الدفع (ledger بسيط vs Payment Entry/GL/خزنة)، الفاتورة (PDF vs Sales Invoice)، الباقة (عميل عام vs عميل+Resource)، الخصم (ضمني vs سطر).
3. **في XStudio وغير موجود في ERP**: نسب المصورين وقفل الأسبوع، `price_pending`، باقات الريلز (وحدة)، الخدمات المخصّصة `svc:`، زيادة العطلة، blocks، عربون محسوب، إشعارات، مصوّر الجلسة، سعر للفرد.
4. **في ERP وغير مدعوم في XStudio**: `No Show`، Revenue Share مع محاضر (Supplier)، الفواتير والـ GL، الخزنة اليومية، الإضافات (مايك/إضاءة) كبنود منفصلة، مراكز التكلفة، باقة مرتبطة بـ Resource، منع تعديل بعد الترحيل، `expected_revenue/attendees`.
5. **قواعد متعارضة**: `Confirmed` ⇄ `Confirmed with Deposit`؛ `Completed` قبل الوقت؛ العميل غير الموجود؛ تعديل الحجز المستورد؛ الباقة لا تُستهلك للمستورد؛ الإلغاء يتطلب سبباً إلزامياً في ERP (XStudio `cancel_note` اختياري).
6. **حقول ناقصة**: ERP: `external_id` على Customer/Studio Hour Package/Usage/Payment، `source_updated_at`, `last_synced_at`, `xstudio_status`, `xstudio_booking_type`, `price_pending`, `deposit_due`, `expires_at`, `unit`, `photographer`; XStudio: `updated_at` على `customer_packages/users`, `people`, `discount`.
7. **علاقات ناقصة**: XStudio booking → ERP Resource (mapping table)؛ XStudio `svc:` → ERP Item؛ `payments.method` → Mode of Payment؛ `photographers` → Employee/Supplier؛ `hall_id` → Resource.
8. **قيم حالة غير متوافقة**: انظر §8.5.
9. **معلومات مالية ناقصة**: XStudio بلا خزنة/مركز تكلفة/حساب؛ ERP بلا `discount`/`price_pending`.
10. **بنية تكامل ناقصة**: ERP بلا scheduler job/HTTP client/credentials store/webhook receiver/mapping tables؛ XStudio بلا pagination/`updatedSince`/API key/webhooks.

---

## 7. Business Logic Differences (اختلافات منطق العمل الجوهرية)

| # | الموضوع | XStudio | IMED ERP | الأثر على التكامل | القرار المقترح |
|---|---|---|---|---|---|
| B1 | **ما الذي يُحجز؟** | قاعة (`hall_id`) + نوع خدمة؛ الكاميرات مورد مشترك عالمي (≤3) | Resource واحد (خدمة أو قاعة)؛ تعارض على Resource+يوم | التعارض في XStudio على القاعة، في ERP على Resource. إن مُثِّل كل نوع خدمة كـ Resource (كما في seed الحالي: "سمارت بورد 86", "ريلز"…) فسيُسمح في ERP بحجزين متداخلين في نفس القاعة (خدمتان مختلفتان) أو يُرفض حجزان مختلفَي القاعة لنفس الخدمة | **Resource = قاعة XStudio** (6 Resources من نوع Studio Service بمركز `استوديو X`). نوع الخدمة → حقل + Item. الـ Resources الحالية في `setup_booking_prices.py:51-57` تُبقى للحجز اليدوي أو تُعطَّل |
| B2 | **معنى الحالة** | `confirmed` = الحجز ثابت (افتراضي لحجز العميل والـ walk-in)؛ `pending` = ينتظر تأكيد العميل؛ لا يعتمد على الدفع | `Confirmed with Deposit` = تلقائي عند `paid_amount > 0` (`refresh_booking`, `booking_accounts.py:192-211`)، ويُشترط `paid_amount>0` | حجز `confirmed` غير مدفوع يجب أن يُستورد `Tentative` | mapping بالحالة + الدفع (§8.5) وحفظ `xstudio_status` |
| B3 | **الدفع** | ledger `payments` (مبلغ، طريقة، من سجّل) بدون حساب/خزنة؛ الاسترداد سطر سالب؛ الخصم ضمني | Payment Entry على Mode of Payment → حساب خزنة بمركز تكلفة؛ Treasury Close يومي يقارن المتوقع بالمعدود | إذا أُنشئت PE من دفعات XStudio، ستدخل `خزينة X Studio` ويجب أن يعدّها الموظف في الإقفال اليومي. إذا سُجِّل الموظف الدفعة أيضاً يدوياً في ERP → تكرار | **قاعدة ذهبية**: مصدر واحد لكل دفعة. إما (أ) كل دفعات الاستوديو تُسجَّل في XStudio فقط وERP يولّد PE منها، أو (ب) ERP هو مكان التسجيل وXStudio للعرض. التوصية (أ) لأن الموظف يعمل في XStudio؛ `record_payment` يرفض المستورد أصلاً |
| B4 | **الفاتورة** | PDF غير محاسبي؛ لا رقم؛ يُولَّد عند الطلب | Sales Invoice مرقَّمة عند Completed (Manual) | هل تُنشأ Sales Invoice للحجز المستورد المكتمل؟ تؤثر على الإيراد في GL | **قرار المالك (Q-B2)**. التوصية: نعم، SI واحدة لكل حجز `completed` بـ `amount_due` (بعد الخصم وتغطية الباقة) بتاريخ الجلسة، في Phase 2 بعد MVP |
| B5 | **الباقة** | عامة للعميل حسب الفئة (`category`)؛ تنتهي بـ `expires_at`; وحدة ساعة أو ريل؛ قد تكون غير مدفوعة | مرتبطة بـ Resource واحد؛ لا انتهاء؛ ساعات فقط؛ Active بعد Submit؛ `make_invoice` اختياري | باقة XStudio بفئة `smart` تُستعمل في قاعات 3/4/6 → في ERP لا يمكن ربطها بـ Resource واحد إن كان Resource = قاعة | **Extend ERP**: حقل `resource` يصبح اختيارياً للمستورد **أو** يُشير إلى Resource "تجميعي" (مثلاً `استوديو X — عام`)؛ `applies_to_category` نص |
| B6 | **إعادة الساعات عند الإلغاء/No Show** | الإلغاء يُعيد كل `hours_deducted` دائماً (حتى الموظف يلغي بعد الموعد) | `draw()` يُعيد عند Cancelled/No Show؛ قرار معلَّق هل No Show يستهلك | متطابق تقريباً؛ لا `No Show` في XStudio | ERP لا يُنشئ No Show للمستورد |
| B7 | **تعديل بعد الترحيل** | أي شيء قابل للتعديل في أي وقت (`amount-due`, `PATCH package`) | `check_posted`: بعد SI/JE لا تعديل | تغيير في XStudio على حجز له SI في ERP → تعارض | قاعدة: ERP يُسجِّل "Changed in Source after posting" في Import Log ويُنبِّه المحاسب؛ لا يعدّل الوثائق المرحَّلة تلقائياً |
| B8 | **الحجوزات اليدوية في ERP على موارد الاستوديو** | — | مسموحة حالياً | تتعارض مع المستوردة | منع يدوي على Resources المُدارة بـ XStudio |
| B9 | **التوقيت** | `timestamptz` UTC في DB؛ الحساب بـ `TZ=Africa/Cairo` | `booking_date` + `Time` محلية (الموقع `Africa/Cairo` مفترض) | تحويل UTC→Cairo إلزامي؛ حجز حتى 24:00 | التحويل في ERP بـ `zoneinfo("Africa/Cairo")`؛ `to_time=00:00` اليوم التالي → `23:59:59` + حفظ الأصل |
| B10 | **الدقة** | `hours numeric(6,2)`, أموال `numeric(10,2)` | `hours` Float 2 (Booking), 4 (Package); Currency 2 | ساعة 1.5 ✅؛ لا كسور أدق من دقيقة | OK؛ مقارنة بتسامح 0.01 |
| B11 | **القاعات (HAL)** | قاعات تصوير | قاعات محاضرات بمحاضر وعدد حضور ونسبة | **لا تقاطع** | HAL يبقى يدوياً في ERP (أو يُراجَع نطاق XStudio مستقبلاً) |
| B12 | **المصورون** | نسبة لكل مصوّر لكل نوع لكل أسبوع | لا شيء | مستحقات غير مسجَّلة في ERP | Mirror + ترحيل لاحق كـ Journal Entry (مصروف `حصة المصورين`؟ حساب غير موجود) |

---

## 8. Data Mapping Matrix (المطابقة على مستوى الحقول)

> **اصطلاح:** `source_system = "xstudio"` ثابت. `import_key = "xstudio:<uuid>"`. كل DocType مستورد يحمل: `source` (Imported), `source_system`, `external_id`, `import_key` (unique), **`source_updated_at`** (Datetime, من `updated_at`/`created_at` في XStudio), **`last_synced_at`** (Datetime, وقت آخر معالجة ناجحة في ERP), `import_log` (Link Integration Import Log). الحقول المعلَّمة **(NEW)** غير موجودة في ERP ويجب إضافتها (Custom Field أو حقل في DocType).

### 8.1 Customer (المدرّس/العميل) — `users WHERE role='customer'` → ERP `Customer`

| XStudio Model | XStudio Field | ERP DocType | ERP Field | Transformation | Missing? |
|---|---|---|---|---|---|
| users | `id` (uuid) | Customer | `xstudio_customer_id` Data unique **(NEW custom field)** | as-is | ✅ NEW |
| users | `name` | Customer | `customer_name` | trim؛ إن تكرر الاسم Frappe يضيف لاحقة في `name` (autoname) → لا مشكلة لأن المفتاح `xstudio_customer_id` | — |
| users | `phone` | Customer | `mobile_no` + `custom_phone_key` (via `customers.normalize_phone`) | إذا يبدأ بـ `no-phone-` → فارغ (عميل بلا هاتف مسموح، `customers.py:15-16`)؛ وإلا `normalize_phone()`. **تعارض**: إن وُجد Customer بنفس `custom_phone_key` ولم يكن له `xstudio_customer_id` → ربطه (link) لا إنشاء جديد؛ إن كان له id آخر → Failed "phone belongs to another XStudio customer" | — |
| users | `email` | Customer | `email_id` | nullable | — |
| users | `address` | Customer | Address (child doc) أو `customer_details` | نص حر → `customer_details` (أبسط) | — |
| users | `notes` | Customer | `customer_details` (append) | | — |
| users | `is_active` | Customer | `disabled` | `NOT is_active` | — |
| — | — | Customer | `customer_group` | ثابت: **قرار** (Q-B1): مجموعة `مدرّس` (غير موجودة في seed؛ الموجود `طالب`, `طبيب`) أو `Individual` | ✅ NEW group |
| — | — | Customer | `customer_type` | `Individual` | — |
| users | `created_at` | Customer | `source_updated_at` **(NEW)** | **لا `updated_at` في XStudio** → حتى M-04 يُستعمل `created_at` ويُعاد جلب كل العملاء كل مزامنة (200 حد → M-04 ضروري) | ✅ |
| users | `role` | — | — | فلتر `= 'customer'` فقط؛ الموظفون لا يُستوردون | — |
| users | `password_hash` | — | **لا يُستورد أبداً** | | — |

### 8.2 Studio hall → `Booking Resource`

| XStudio | Field | ERP | Field | Transformation |
|---|---|---|---|---|
| halls | `id` (1,3,4,5,6,8) | Booking Resource | `xstudio_hall_id` Int **(NEW)** | mapping table ثابت يُنشأ مرة واحدة (6 صفوف) |
| halls | `name` | Booking Resource | `resource_name` | مثلاً `X Studio — Hall 3` |
| — | — | Booking Resource | `resource_type` | `Studio Service` (ليس Hall) |
| — | — | Booking Resource | `cost_center` | `استوديو X - MMG` |
| — | — | Booking Resource | `item` | `STUDIO-HOUR` (للعرض؛ التسعير لا يُطبَّق على المستورد) |
| halls | `is_active` | Booking Resource | `disabled` | `NOT` |
| halls | `price_per_hour`, `open/close_minute`, `has_screen`, `equipment` | Booking Resource | `equipment` / `notes` | نصي للعرض فقط |
| — | — | Booking Resource | `managed_by_source` Select **(NEW)** | `XStudio` → يمنع الحجز اليدوي |

### 8.3 Booking type → Item / label (جدول mapping قابل للتعديل: **(NEW)** DocType `XStudio Service Map`)

| XStudio `booking_type` | ERP Item (موجود في `setup_booking_prices.py`) | ملاحظة |
|---|---|---|
| `session` | `STUDIO-HOUR` | |
| `smartboard` + `screen_size=86` | `STU-SB86-*`؟ لا Item ساعة لـ 86 (الموجود باقات فقط) → `STUDIO-HOUR` أو Item جديد `STU-SB86-HOUR` | ✅ NEW item |
| `smartboard` + `screen_size=75` | `STU-SB75-HOUR` | |
| `podcast` + `cameras=1/2/3` | `STU-PODCAST-1CAM/2CAM/3CAM` | **أسعار مختلفة** بين النظامين (800/1250/1575 vs 1250/1750/2250) → السعر يؤخذ من XStudio |
| `reels` | `STU-REEL-1` | flat per booking |
| `hall_rental` | `STUDIO-HOUR` (أو Item جديد `STU-HALL-RENTAL`) | ✅ NEW |
| `location_rental` | Item جديد `STU-LOCATION-HOUR` (450/h) | ✅ NEW |
| `svc:<id>[#n]` | صف في `XStudio Service Map` (`service_id`, `option_index`, `title` من `/api/config`, `item`) | غير معروف مسبقاً → الاستيراد يُنشئ الصف بـ `item` فارغ ويُعلِّم "needs mapping"; الحجز يُستورد بـ Item افتراضي `STUDIO-HOUR` |

### 8.4 Booking → ERP `Booking`

| XStudio Model | XStudio Field | ERP DocType | ERP Field | Transformation | Missing? |
|---|---|---|---|---|---|
| bookings | `id` | Booking | `external_id`; `import_key="xstudio:"+id` | | موجود |
| — | `"xstudio"` | Booking | `source_system`; `source=Imported` | | موجود (لكن Import Log Select يقبل `booking` فقط → استعمال `booking` في Log أو إضافة `xstudio` للـ Select **(NEW option)**) |
| bookings | `hall_id` | Booking | `resource` | via `XStudio Resource Map` | mapping NEW |
| bookings | `customer_id` | Booking | `customer` | via `Customer.xstudio_customer_id`؛ إن NULL (walk-in قديم بلا هاتف) → fallback بـ `customer_phone` normalize → وإلا Customer placeholder "عميل XStudio بلا حساب"? → **قرار (Q-B1)** | |
| bookings | `customer_name`, `customer_phone` | Booking | `xstudio_customer_name`, `xstudio_customer_phone` Data **(NEW)** | snapshot وقت الحجز (قد يختلف عن Customer) | ✅ |
| bookings | `starts_at` (timestamptz) | Booking | `booking_date` + `from_time` | تحويل إلى `Africa/Cairo`؛ `date = local.date()`, `from_time = local.time()` | |
| bookings | `ends_at` | Booking | `to_time` | محلي؛ إن `ends_at.date() > starts_at.date()`: إذا `ends_at` = منتصف الليل بالضبط → `23:59:59`؛ وإلا Failed "crosses midnight" | |
| bookings | `starts_at`, `ends_at` | Booking | `xstudio_starts_at`, `xstudio_ends_at` Datetime **(NEW)** | UTC الأصلي للمطابقة | ✅ |
| bookings | `hours` | Booking | `hours` | ERP يحسبها من الأوقات (`check_times`)؛ مقارنة بتسامح 0.02 (حالة 23:59:59) | |
| bookings | `status` + `amount_paid` | Booking | `status` | §8.5 | |
| bookings | `status` | Booking | `xstudio_status` Select **(NEW)** | `pending/confirmed/completed/cancelled` كما هي | ✅ |
| bookings | `booking_type`, `screen_size`, `cameras`, `session_type` | Booking | `xstudio_booking_type` Data, `xstudio_screen_size` Int, `xstudio_cameras` Int **(NEW)** + `xstudio_service_item` Link [Item] (via Service Map) | | ✅ |
| bookings | `price_total` | Booking | `total_amount` | **قرار دلالي**: `total_amount` في ERP = ما يُطلب من العميل مالياً. التوصية: `total_amount = price_total` (السعر الكامل) و`amount_due` يُخزَّن منفصلاً؛ لكن `check_amounts` يشترط `paid ≤ total` ✅ و`outstanding = total − paid` ❌ سيُظهر تغطية الباقة والخصم كمستحقات. **البديل الموصى به**: `total_amount = amount_due` (المطلوب فعلاً) + حقول جديدة `xstudio_price_total`, `xstudio_discount_amount` | ✅ NEW fields |
| bookings | `amount_due` | Booking | `total_amount` (موصى) | | |
| bookings | `amount_paid` | Booking | `paid_amount` | `check_amounts`: `paid ≤ total`؛ XStudio يسمح `amount_paid > amount_due` (دفع زائد) → Failed أو clamp + تحذير. **قرار** | |
| bookings | `payment_status` | Booking | `xstudio_payment_status` Select **(NEW)** | `unpaid/partial/paid/refunded` | ✅ |
| bookings | `price_pending` | Booking | `price_pending` Check **(NEW)** | | ✅ |
| bookings | `deposit_due` | Booking | `deposit_due` Currency **(NEW)** | | ✅ |
| bookings | `package_id`, `hours_deducted` | Booking | `hour_package` (via `Studio Hour Package.external_id`), `package_hours` | حالياً `check_hour_package` يرفض الباقة للمستورد (`booking.py:102-103`) → يُعدَّل | تعديل منطق |
| bookings | `cancelled_by`, `cancel_note` | Booking | `cancellation_reason` | `f"{cancel_note or 'Cancelled in XStudio'} (by {cancelled_by})"` (إلزامي عند Cancelled) | |
| bookings | `notes` | Booking | `notes` | | |
| bookings | `photographer_id` | Booking | `xstudio_photographer` Link [XStudio Photographer] **(NEW)** | | ✅ |
| bookings | `created_by` | Booking | `xstudio_created_by` Data **(NEW)** (اسم الموظف من users) | اختياري | ✅ |
| bookings | `created_at` | Booking | `creation`؟ لا (Frappe system) → `xstudio_created_at` **(NEW)** | | ✅ |
| bookings | `updated_at` | Booking | `source_updated_at` **(NEW)** | | ✅ |
| — | — | Booking | `last_synced_at` **(NEW)** | now() في ERP | ✅ |
| — | — | Booking | `cost_center`, `resource_type` | fetch من Resource (`استوديو X`) | |
| — | — | Booking | `rental_model`, `activity`, `responsible_*`, `lecturer*` | **لا تُملأ** (Resource ليس Hall) | |

### 8.5 خريطة الحالات

| XStudio `status` | XStudio `amount_paid` | ERP `status` | ملاحظة |
|---|---|---|---|
| `pending` | أي | `Tentative` | |
| `confirmed` | `= 0` | `Tentative` | XStudio يعتبره مؤكداً؛ ERP لا يستطيع (`check_status`) إلا بتعديل: **بديل**: السماح للمستورد بـ `Confirmed with Deposit` بدون دفع؟ لا — يُفسد دلالة ERP. يُحفظ الأصل في `xstudio_status` |
| `confirmed` | `> 0` | `Confirmed with Deposit` | |
| `completed` | أي | `Completed` | إن `starts_at > now()` ERP يرفض (`booking.py:296`) → Failed |
| `cancelled` | أي (قد تكون `refunded`) | `Cancelled` | `cancellation_reason` إلزامي |
| — | — | `No Show` | لا يُنتَج من XStudio |

**Payment status** (`unpaid/partial/paid/refunded`) ↔ ERP لا يملك حالة دفع صريحة (مشتقة من `outstanding_amount`) → تُحفظ كما هي في `xstudio_payment_status`.

### 8.6 Package → `Studio Hour Package`

| XStudio | Field | ERP | Field | Transformation | Missing? |
|---|---|---|---|---|---|
| customer_packages | `id` | Studio Hour Package | `external_id`, `import_key`, `source`, `source_system` **(NEW على هذا DocType)** | | ✅ |
| customer_packages | `customer_id` | SHP | `customer` | via `xstudio_customer_id` | |
| customer_packages | `template_id` + `package_templates.category/name` | SHP | `xstudio_template_id`, `xstudio_category`, `package_name` **(NEW)** | | ✅ |
| customer_packages | `name` | SHP | `notes` أو `package_name` (NEW) | | ✅ |
| customer_packages | `hours_total` | SHP | `hours_purchased` | **إذا category = reels → `unit = Reel`** | `unit` NEW |
| customer_packages | `hours_remaining` | SHP | `hours_remaining` (computed from usage) | **لا يُكتب مباشرة**؛ يُقارَن بعد استيراد الـ usage → فرق = "manual adjustment in XStudio" → سطر Usage تعويضي بـ reason `XStudio manual adjustment` **أو** تنبيه فقط (**قرار**) | |
| customer_packages | `price` | SHP | `price` | | |
| customer_packages | `payment_status` | SHP | `xstudio_payment_status` **(NEW)** | | ✅ |
| customer_packages | `purchased_at` | SHP | `purchase_date` (Cairo date) + `xstudio_purchased_at` | | |
| customer_packages | `expires_at` | SHP | `expires_on` Date **(NEW)** | nullable | ✅ |
| — | — | SHP | `resource` (reqd) | **مشكلة**: الباقة في XStudio ليست لقاعة. حلّ: Resource تجميعي `X Studio — Packages` **أو** جعل `resource` غير إلزامي للمستورد (**قرار تصميمي**: الأول أبسط ولا يغيّر الـ validations) | تعديل |
| — | — | SHP | `status` | `Active` إذا `hours_remaining>0` و(لا `expires_at` أو > now)؛ `Used Up` إذا `=0`؛ `Cancelled` إذا حُذفت في XStudio (soft delete) — **ERP يعرّف الحالة عبر docstatus/submit**: المستورد يُدرج ويُرسل (submit) تلقائياً بـ `ignore_permissions` | |
| — | `payments[package_id]` | SHP | `sales_invoice` | لا يُنشأ في MVP | |
| customer_packages | (لا updated_at) | SHP | `source_updated_at` | من M-03؛ حتى ذلك الوقت = max(`purchased_at`, آخر `payments.created_at`, آخر `package_usage.created_at`) | |

### 8.7 Package usage → `Studio Hour Package Usage` (child)

| XStudio `package_usage` | ERP Usage child | Transformation |
|---|---|---|
| `id` | `external_id` Data **(NEW على الchild)** | منع تكرار السطر |
| `package_id` | parent | |
| `booking_id` | `booking` | via Booking `import_key`؛ إن لم يُستورد الحجز بعد → يُستورد الحجز أولاً (ordering: customers → packages → bookings → usage → payments) |
| `hours` (+/−) | `hours` | نفس الإشارة (ERP: فوق الصفر سحب، تحت الصفر إعادة ✅ متطابق) |
| `reason` (`booking`, `cancel_refund`) | `reason` | `"XStudio: booking"`, `"XStudio: cancel refund"` |
| `created_at` | `changed_on` | Cairo |
| — | `changed_by` | المستخدم التكاملي |
| — | `balance` | محسوب تراكمياً في ERP (`record()`) |

> **ملاحظة تنفيذية:** `Studio Hour Package.record()` (`studio_hour_package.py:155-187`) يرفض الرصيد السالب ويحدّث الحالة. يُستعمل كما هو مع flag `from_import` بدل إعادة الكتابة.

### 8.8 Payments → **(NEW)** DocType `XStudio Payment` (mirror) ثم اختيارياً Payment Entry

| XStudio `payments` | ERP `XStudio Payment` (NEW) | ثم Payment Entry (Phase 2) |
|---|---|---|
| `id` | `external_id`, `import_key` unique | `custom_booking_request = "xstudio:"+id` (الحقل unique موجود `booking_accounts.py:40-86`) → idempotency مجانية |
| `booking_id` / `package_id` | `booking` Link / `hour_package` Link | `custom_booking` |
| `amount` (سالب = refund) | `amount`, `direction` = `Receive|Refund` | `payment_type = Receive` أو `Pay` (refund) |
| `method` | `method` Data | `mode_of_payment` via **(NEW)** `XStudio Payment Method Map`: `cash→نقدي — استوديو X`, `instapay→InstaPay`, `transfer→?`, `other→?`, `refund→(نفس طريقة الأصل؟ غير معروف)` → **قرار Q-B5** |
| `recorded_by` | `recorded_by_name` | `remarks` |
| `created_at` | `posted_at` (Cairo), `source_updated_at` | `posting_date` = تاريخ الدفع (لا مستقبلي: `dates.refuse_future_date`) — **تحذير**: دفعة بتاريخ يوم مُقفَل في Treasury Close → `treasury_close.check_closed_days` يرفض → تُسجَّل Failed وتُعرض للمحاسب |
| — | `status` = `Mirrored | Posted | Skipped | Failed` | |

### 8.9 Photographers & week closings → **(NEW)** `XStudio Photographer`, `XStudio Week Closing`

| XStudio | ERP (NEW) |
|---|---|
| `photographers.id/name/is_active` | `XStudio Photographer` (`external_id`, `photographer_name`, `disabled`, `employee` Link [Employee] اختياري، `supplier` Link اختياري) |
| `week_closings.week_start` (PK) | `XStudio Week Closing` (`week_start` unique, `closed_at`, `closed_by_name`, `base`, `total_cut`, `totals_json`, child `lines` = photographer, bucket, count, amount, pct, cut) |
| `data.lines[]` | child rows |
| `closed_at` | `source_updated_at` (يُعاد الاستيراد إذا تغيّر) |
| — | `journal_entry` Link (Phase 2: ترحيل المستحقات) |

### 8.10 المعرّفات والحقول التكاملية الموحَّدة (لكل DocType مستورد)

| الحقل | النوع | الغرض |
|---|---|---|
| `source` | Select Manual/Imported | موجود على Booking؛ يُضاف للباقي |
| `source_system` | Data = `xstudio` | |
| `external_id` | Data (uuid) | |
| `import_key` | Data unique = `xstudio:<uuid>` | منع التكرار على مستوى DB |
| `source_updated_at` | Datetime | آخر تغيير في المصدر (للكشف عن التحديثات، وللـ optimistic ordering: لا يُطبَّق تحديث أقدم من المخزَّن) |
| `last_synced_at` | Datetime | آخر مرة عولج فيها السجل بنجاح |
| `import_log` | Link Integration Import Log | أي تشغيل أدخله/غيّره آخر مرة |
| `source_payload_hash` | Data (sha256 للـ JSON المطبَّع) | اختصار المقارنة: إن تطابق الـ hash → skipped بلا مقارنة حقول |

### 8.11 أنواع البيانات والدلالات — نقاط حرجة

- **المنطقة الزمنية**: XStudio يخزّن UTC (`timestamptz`) ويعرض Cairo. ERP يخزّن محلياً. التحويل في ERP عبر `zoneinfo`. **لا يُفترض أن `starts_at.slice(0,10)` هو التاريخ المحلي** (Excel sync في XStudio نفسه يرتكب هذا الخطأ `excelSync.js:58` بـ `toISOString()`).
- **24:00**: `close_minute=1440` يسمح بـ `ends_at` = منتصف الليل التالي بالضبط.
- **العملة**: EGP ضمنياً في XStudio (لا عمود عملة)؛ ERP: عملة الشركة MMG. لا تحويل.
- **`hours` للريلز** = عدد الريلز في `customer_packages`، لكن `bookings.hours` = مدة فعلية بالساعات؛ `hours_deducted=1` لريل واحد. **لا تخلط**.
- **`amount_paid` قد يتجاوز `amount_due`** (XStudio `pay` لا يمنع) → ERP `check_amounts` يرفض `paid > total`.
- **`price_pending=true`** → `price_total=0`, `amount_due=0`؛ قد تُسجَّل دفعات لاحقاً فتصبح `amount_paid > amount_due = 0` → ينطبق السابق. يجب أن يتعامل الاستيراد مع هذه الحالة صراحةً: `total_amount = max(amount_due, amount_paid)` + علم `price_pending`.
- **NULLs**: `customer_id` nullable؛ `package_id` nullable؛ `screen_size/cameras` nullable؛ `email` nullable؛ `expires_at` nullable (= لا تنتهي؛ **لا تُحوَّل إلى تاريخ بعيد**).
- **Customer identity**: المفتاح الأساسي `xstudio_customer_id`؛ الهاتف للربط الأولي فقط. تغيير الهاتف في XStudio (`PATCH /customers/:id`) يحدّث ERP `mobile_no` بعد التأكد من عدم تعارض `custom_phone_key`.
- **رسائل الخطأ** عربية بشرية → لا parsing؛ الاعتماد على HTTP status + `error` كنص للسجل.

---

## 9. Recommended Integration Architecture (المعمارية الموصى بها)

### 9.1 تقييم البدائل

| المعيار | (1) Scheduled polling من ERP | (2) Webhooks من XStudio | (3) Hybrid |
|---|---|---|---|
| ما يتطلبه من XStudio | 3–4 endpoints قراءة + دور/مفتاح (M-00..M-04) — **صغير** | M-00 + M-07 (جدول deliveries, retry, HMAC, استدعاء بعد كل commit في ~12 موضعاً) — **متوسط/كبير** | كلاهما تدريجياً |
| ما يتطلبه من ERP | HTTP client + scheduler job + mapping/staging + Import Log — **متوسط** | whitelisted receiver + التحقق + نفس المعالجة | كلاهما |
| زمن الظهور في ERP | = فترة الـ polling (5–15 دقيقة) | ثوانٍ | ثوانٍ مع شبكة أمان |
| المتانة | عالية (ERP يسحب ما فاته بـ `updatedSince`) | ضعيفة وحدها (فقدان رسالة = فقدان تحديث؛ XStudio على Railway بلا queue) | عالية |
| الكشف عن التعديلات الصامتة | يعتمد على `updated_at` (ناقص على packages/users حتى M-03/M-04) | فقط ما يُطلق حدثاً | كلاهما |
| اعتماد ERP على توفر XStudio | يتحمّل الانقطاع | XStudio يتحمّل انقطاع ERP بـ retry | |
| **التوصية** | **MVP** | لاحقاً | **الهدف النهائي** |

**القرار:** **Hybrid على مرحلتين.** المرحلة 1 (MVP): polling من ERP كل **10 دقائق** (قابل للضبط) + مزامنة كاملة ليلية (full reconciliation pull). المرحلة 2: webhook من XStudio يُطلق "مزامنة فورية مُستهدَفة" لنفس السجل عبر نفس كود المعالجة؛ الـ polling يبقى.

### 9.2 إجابات الأسئلة المحدَّدة

| السؤال | الجواب |
|---|---|
| من يبدأ المزامنة؟ | **ERP** (scheduler `imed_erp.integrations.xstudio.sync.run_incremental` كل 10 دقائق، `run_full` يومياً 03:30). Phase 2: XStudio يرسل webhook يستدعي `run_targeted(entity, id)`. |
| مصدر الحقيقة لكل كيان | **XStudio**: الحجز (أوقات/حالة/قاعة/نوع/سعر/مستحق/مدفوع)، الباقة ورصيدها وledger، العميل (اسم/هاتف)، دفعات الاستوديو (ledger)، المصورون ونسبهم. **ERP**: الوثائق المحاسبية (PE/SI/JE)، الخزنة والإقفال اليومي، مراكز التكلفة، تصنيف الـ Items، قاعات Imed (HAL) بالكامل، Customer master للحقول غير المشتركة (مجموعة، عناوين إضافية). |
| سرعة الظهور | MVP: ≤ 10 دقائق. Phase 2: ثوانٍ. |
| هل XStudio يدعم webhooks؟ | **لا** (لا كود). |
| فلتر `updated_at`؟ | **لا** في أي endpoint حالي. `bookings.updated_at` موجود في الـ DB فقط (يُرجع ضمن `b.*` لكن لا يُفلتر). → M-01. |
| Pagination؟ | **لا**. حدود ثابتة 500/200/100/8. → M-01..M-04. |
| تمثيل الملغي | صف يبقى بـ `status='cancelled'` + `cancelled_by/cancel_note`; الساعات تعود بسطر `package_usage` سالب؛ المال يُسترد بسطر `payments` سالب `method='refund'` + `payment_status='refunded'`. **لا حذف**. |
| المحذوف | **الحجوزات لا تُحذف أبداً**. **الباقات تُحذف فعلياً** (`DELETE /customer-packages/:id`) ومعها ledger، والعملاء بلا حجوزات تُحذف. ERP يكتشف الاختفاء في الـ full pull الليلي ("missing in source") ويُعلِّم السجل `Cancelled` مع reason "deleted in XStudio" **بدون** حذف. → مطلوب soft delete في XStudio (Q-X5). |
| منع التكرار | `import_key` unique على كل DocType مستورد + `custom_booking_request` unique على Payment Entry + معاملة لكل سجل (savepoint) + فحص `source_updated_at` قبل التحديث. |
| فشل طلب API | retry 3× بـ backoff (2s, 8s, 30s) داخل التشغيل؛ عند استمرار الفشل → Import Log `Failed` مع `message` = HTTP status، لا تغيير في `last_cursor`؛ تنبيه بعد 3 تشغيلات فاشلة متتالية (Notification للمحاسب + سطر أحمر في Integration Status). |
| فشل سجل واحد | savepoint per record (موجود في `booking_import.py:36-68`) → `failed(row_no, external_id, reason)` في Import Log؛ باقي السجلات تُستكمل؛ **لكن الـ cursor لا يتقدم فوق `source_updated_at` لأقدم سجل فاشل** (أو: يتقدم ويُسجَّل الفاشل في جدول `retry queue` يُعاد كل تشغيل حتى 10 مرات ثم يُعلَّم "needs attention"). التوصية: **retry queue** حتى لا يعلّق سجل واحد التدفق كله. |
| الاستئناف بعد انقطاع | `XStudio Sync State` (single DocType): `bookings_cursor`, `payments_cursor`, `packages_cursor`, `usage_cursor`, `customers_cursor`, كلٌّ = آخر `(source_updated_at, id)` معالَج بنجاح. يُحفظ بعد كل صفحة. التشغيل التالي يبدأ منه. overlap آمن (idempotent). |
| كشف التحديثات المفقودة | (أ) full pull ليلي يقارن `source_payload_hash`؛ (ب) تقرير مطابقة §14؛ (ج) M-06 audit feed اختياري. |
| الاستيراد التاريخي الأول | خياران: (أ) `GET /api/admin/export` مرة واحدة (JSON كامل، يحتاج super_admin، يُخرج hashes → يُستعمل من جهاز المحاسب ثم يُرفع إلى ERP عبر شاشة "Import XStudio Snapshot" وتُحذف النسخة) أو (ب) الـ polling نفسه بـ `updatedSince=1970-01-01` بصفحات (يتطلب M-01). التوصية **(ب)** إن أُنجز M-01 قبل الإطلاق؛ وإلا (أ) مع تنقية `users.password_hash` قبل الرفع. الترتيب: halls → customers → package templates → customer_packages → bookings → package_usage → payments → photographers → week_closings. |
| التحديثات التزايدية | كل 10 دقائق: `bookings?updatedSince=cursor−5min` (تداخل 5 دقائق للأمان)، ثم `payments?since`, `package-usage?since`, `customer-packages?updatedSince`, `customers?updatedSince`. المعالجة بالترتيب أعلاه داخل التشغيل. |

### 9.3 مكوّنات ERP المقترَحة (كلها **NOT YET IMPLEMENTED**)

```
apps/imed_erp/imed_erp/integrations/xstudio/
├── settings.py        # XStudio Settings (Single): base_url, auth_mode (password|api_key), username, password (Password), api_key (Password), poll_interval, enabled, webhook_secret (Password), default_customer_group, mapping defaults
├── client.py          # HTTP client (requests), token cache + refresh, retry/backoff, pagination iterator, timeouts 15s, no secrets in logs
├── state.py           # XStudio Sync State (Single): cursors per entity, last_success_at, last_attempt_at, consecutive_failures
├── sync.py            # run_incremental(), run_full(), run_targeted(entity, id); يفتح ImportRun ويغلقه
├── mappers/           # customers.py, resources.py, bookings.py, packages.py, usage.py, payments.py, photographers.py, week_closings.py (pure functions: XStudio JSON → ERP values)
├── writers/           # upsert_customer(), upsert_booking() (يستدعي booking_import منطق المقارنة), upsert_package(), append_usage(), mirror_payment(), ...
├── posting.py         # Phase 2: make_payment_entry(mirror) / make_sales_invoice(booking) تحت قواعد §12
├── reconcile.py       # §14
├── webhook.py         # Phase 2: whitelisted receiver + HMAC
└── doctype/           # XStudio Resource Map, XStudio Service Map, XStudio Payment Method Map, XStudio Payment, XStudio Photographer, XStudio Week Closing (+child), XStudio Sync Retry
```

- يُعاد استعمال: `integration_import_log.ImportRun`, `booking_import.differences()/booking_values()` (بتوسيعها), `customers.normalize_phone/customer_with_phone`, `studio_hour_package.record()`, `booking_accounts.record_payment()` (Phase 2 بـ `request_id`), تقرير `Integration Status` (إضافة صف `xstudio`).
- Scheduler في `hooks.py`: `"cron": {"*/10 * * * *": ["...sync.run_incremental"], "30 3 * * *": ["...sync.run_full", "...reconcile.run_daily"]}`.
- مستخدم `integration-xstudio@imed.local` بدور **Integration Runner** (جديد) + User Permission على Cost Center `استوديو X`؛ كل الكتابات بـ `frappe.set_user(integration_user)` لا Administrator (قابلية التتبع).

---

## 10. Synchronization and Event Handling (المزامنة ومعالجة الأحداث)

### 10.1 دورة التشغيل التزايدي (كل 10 دقائق)

1. `ImportRun("xstudio")` يبدأ (Import Log `started_at`, `run_by`).
2. `GET /api/health` → إن فشل: `abort()` بعد retries، `consecutive_failures++`.
3. تجديد التوكن إن انتهى (login بكلمة السر المخزَّنة Password field) أو استعمال API key.
4. لكل كيان بالترتيب (customers → packages → bookings → usage → payments → photographers → week closings): سحب الصفحات من `cursor − overlap`؛ لكل سجل: savepoint → mapper → writer → `inserted()/changed()/skipped()/failed()`؛ تحديث cursor بعد كل صفحة.
5. معالجة `XStudio Sync Retry` queue (السجلات الفاشلة سابقاً، حتى 10 محاولات).
6. `finish()` → `Completed`/`Completed with Errors`؛ تحديث `last_success_at`.

### 10.2 أحداث XStudio ↔ أثرها في ERP

| حدث في XStudio | كيف يُكتشف (MVP polling) | أثره في ERP (MVP) | أثره المالي (Phase 2، حسب القرار) |
|---|---|---|---|
| إنشاء حجز (`booking.create`) | `bookings.updated_at` جديد | Booking جديد `Imported`؛ إن `package_id` → ربط الباقة + Usage row | لا شيء |
| تأكيد العميل | `updated_at` | `xstudio_status=confirmed`; ERP status حسب الدفع | لا شيء |
| دفعة على حجز (`booking.pay`) | `payments.created_at` + `bookings.updated_at` | `XStudio Payment` mirror + تحديث `paid_amount` → `Confirmed with Deposit` | Payment Entry (Receive) إلى Mode of Payment المطابق، `custom_booking_request="xstudio:<payment id>"` |
| تعديل المستحق/خصم | `updated_at` | تحديث `total_amount`, `xstudio_discount_amount`; إن مرحَّل → "Changed after posting" | لا تعديل آلي للوثائق المرحَّلة؛ تنبيه |
| إلغاء | `updated_at` | `Cancelled` + reason؛ Usage سطر سالب (من ledger XStudio) | إن استرداد → Payment Entry (Pay) عكسي؛ إن SI موجودة → Credit Note؟ (**قرار**) |
| نقل الموعد | `updated_at` | تحديث date/time (يُعاد `check_overlap`) | لا شيء إن لم تُرحَّل؛ وإلا تنبيه |
| تطبيق باقة على حجز قائم | `updated_at` + usage row | ربط + Usage | إن SI موجودة بالكامل → تعارض → تنبيه |
| إكمال (`complete`) | `updated_at` (+ payment) | `Completed` | Sales Invoice (إن قُرِّر) بـ `total_amount` + تسوية الدفعات كـ advances |
| تعيين مصوّر | `updated_at` | `xstudio_photographer` | — |
| بيع باقة | `customer_packages` جديد (`purchased_at`) + payment | SHP جديد Submitted Active | Payment Entry على `package`; SI للباقة (قرار revenue timing) |
| دفعة على باقة | `payments.created_at` | mirror + `xstudio_payment_status` | PE |
| تعديل باقة يدوياً | **غير مكتشف** حتى M-03؛ full pull يكشف فرق `hours_remaining` | تنبيه مطابقة أو Usage تعويضي (قرار) | — |
| حذف باقة | اختفاء من full pull | SHP → Cancelled بسبب "deleted in XStudio" (لا حذف) | تنبيه |
| إنشاء/تعديل عميل | `created_at` (M-04 لـ updated) | Customer upsert | — |
| قفل أسبوع | `week_closings.closed_at` | XStudio Week Closing upsert | JE مستحقات مصورين (Phase 3/قرار) |
| تغيير أسعار/خدمات | `GET /api/config` كل تشغيل | تحديث `XStudio Service Map` titles؛ صفوف جديدة "needs mapping" | — |

### 10.3 التعامل مع الحجز المستورد في واجهة ERP

- يبقى **read-only** (موجود: `booking.js:42-52`) مع رابط "Open in XStudio" (`https://www.xstudioeg.com/admin.html`؟ لا deep link بالـ id في XStudio حالياً → **Q-X6**).
- أزرار `Record Payment/Mark Completed/Cancel` مخفية للمستورد (موجود جزئياً: `record_payment` يرفض). يُضاف زر "Re-sync from XStudio" يستدعي `run_targeted("booking", external_id)`.

---

## 11. Authentication and Security (المصادقة والأمان)

| البند | الوضع الحالي | التوصية |
|---|---|---|
| **مصادقة ERP → XStudio** | JWT 7 أيام عبر كلمة سر؛ لا API keys | **M-00**: API key بـ `X-Api-Key` لحساب `integration` (قراءة فقط). إلى أن يُنجز: حساب `accountant`؟ **لا** (له `payments.write`). استعمال `viewer` غير كافٍ (لا packages/customers/reports). → M-00 شرط للإطلاق أو قبول مؤقت لحساب `manager` مع **مخاطرة** write |
| **تخزين الأسرار في ERP** | لا يوجد | DocType `XStudio Settings` (Single) بحقول `Password` (مشفَّرة في DB بمفتاح `encryption_key` من site_config). **لا** في `site_config.json` نصاً. لا تُطبع في logs (`client.py` يُخفي headers) |
| **صلاحيات ERP** | لا دور تكاملي | دور `Integration Runner`: create/write على Booking, Customer, Studio Hour Package, XStudio *, Integration Import Log (عبر flags), read على Items/Resources. User Permission على Cost Center `استوديو X`. لا صلاحية على Payment Entry في MVP (Phase 2: عبر `record_payment` كـ Administrator بالآلية الموجودة `system_user.as_administrator`) |
| **Webhook auth (Phase 2)** | — | HMAC-SHA256 على الجسم بسر مشترك + `X-XStudio-Timestamp` (± 300s) + `X-XStudio-Delivery` uuid مخزَّن 7 أيام لمنع replay؛ endpoint `allow_guest=True` **فقط** لهذا الميثود مع rate limit |
| **HTTPS** | XStudio خلف Railway TLS؛ ERP محلي حالياً | إلزامي للطرفين في الإنتاج؛ ERP يرفض `base_url` غير https |
| **Rate limits** | XStudio: فقط auth | الـ polling ≤ 10 طلبات/تشغيل؛ `limit=500`؛ احترام `Retry-After` |
| **Logging** | XStudio: console؛ ERP: Import Log | ERP: Import Log لكل تشغيل + `frappe.log_error` للاستثناءات بدون payload كامل (أسماء/هواتف مُقنَّعة) |
| **Data privacy** | `GET /api/admin/export` يُسرِّب `password_hash` | F-06؛ ERP لا يخزّن إلا ما يحتاجه (لا email إن لم يُطلب، لا notes طويلة؟ → **قرار**) |
| **Secret rotation** | — | API key قابل للإبطال (`revoked_at`)؛ إجراء موثَّق |
| **Error handling** | رسائل عربية | ERP يُسجِّل status + body ≤ 500 حرف |
| **Exposure of customer info** | | التكامل server-to-server فقط؛ لا يُعرض شيء للعملاء |
| **Account lockout** | 20 محاولة/15 دقيقة على login | تجديد التوكن يحدث مرة/أسبوع → لا خطر؛ لكن بـ API key يُلغى تماماً |

---

## 12. Financial and Accounting Considerations (الاعتبارات المالية والمحاسبية)

### 12.1 المبدأ

**الحجز المستورد لا يُنشئ أي وثيقة محاسبية في MVP.** هذا هو السلوك الحالي في ERP (`booking_accounts.complete/refresh_booking` تتخطى Imported) وهو **آمن**. الترحيل الآلي يُفعَّل في Phase 2 **لكل نوع وثيقة على حدة** بقرار صريح من المالك/المحاسب، بعد شهر على الأقل من المطابقة اليدوية.

### 12.2 أين تُنشأ الوثائق ومن أي حدث (Phase 2 — مقترح)

| الوثيقة | الحدث المُطلِق | المصدر | الشرط | الـ idempotency key |
|---|---|---|---|---|
| **Payment Entry (Receive)** | سطر `payments.amount > 0` | `XStudio Payment` mirror بحالة `Mirrored` | mode-of-payment mapping موجود؛ تاريخ الدفع ليس في يوم مُقفَل (Treasury Close)؛ الحجز/الباقة موجود في ERP؛ `amount ≤ outstanding` (أو يُسجَّل كـ "unapplied advance" — **قرار**) | `custom_booking_request = "xstudio:<payment.id>"` (unique) |
| **Payment Entry (Pay) / Refund** | `payments.amount < 0` (`method='refund'`) | mirror | يوجد PE أصلي؛ طريقة الدفع = نفس طريقة الأصل (غير معروفة في XStudio → **افتراض: cash**) | نفسه |
| **Sales Invoice** | `bookings.status = completed` **و** `price_pending = false` | Booking | Items من Service Map؛ `total = amount_due` (بعد تغطية الباقة والخصم)؛ إن `amount_due = 0` (باقة كاملة) → **لا SI** (الإيراد اعترف به عند بيع الباقة إن قُرِّر "revenue at sale") أو SI بصفر (**قرار Q-B4**) | `custom_booking` + فحص وجود SI غير ملغاة |
| **Sales Invoice لبيع باقة** | SHP جديد | SHP | قرار revenue at sale vs deferred | `Studio Hour Package.sales_invoice` |
| **Journal Entry مستحقات مصورين** | `week_closings.closed_at` | Week Closing | حساب مصروف + حساب مستحقات للمصورين (**غير موجود في COA**: الموجود `حصة المحاضرين`/`مستحقات للمحاضرين`) | `XStudio Week Closing.journal_entry` |

### 12.3 ما لا يُفترض أبداً

- إنشاء الحجز ≠ دفع. (`confirmed` بلا `amount_paid` شائع.)
- `completed` ≠ مدفوع (`complete` بـ `amountPaid=0` مسموح؛ `unpaid-past` report موجود لهذا السبب).
- `payment_status='paid'` ≠ تساوي المبالغ (`settle=true` يجعلها paid بخصم ضمني).
- `hours_remaining` ≠ `hours_total − Σusage` دائماً (التعديل اليدوي).

### 12.4 الحدود المعاملاتية (Transactional boundaries)

- **سجل واحد = savepoint واحد** (نمط `booking_import.py`). الحجز + سطر Usage المرتبط به في نفس الـ savepoint.
- **ترحيل مالي = معاملة منفصلة** لاحقة للمزامنة (job ثانٍ `posting.run`) تقرأ mirrors بحالة `Mirrored` وتُرحِّل واحداً واحداً؛ الفشل يُعلِّم `Failed` بالسبب ولا يوقف الباقي.
- الـ cursor يتقدم فقط بعد commit الصفحة.

### 12.5 المخاطر المالية وضوابطها

| الخطر | الضابط |
|---|---|
| تكرار PE | `custom_booking_request` unique + `payments.id` ثابت |
| تكرار SI | فحص `Sales Invoice.custom_booking` غير ملغاة قبل الإنشاء؛ lock صف الحجز (`complete()` يفعل ذلك) |
| تكرار إيراد (SI للحجز + SI للباقة) | قاعدة واحدة: إيراد الباقة عند البيع ⇒ الحجز المغطى بالباقة **بلا** SI؛ أو deferred ⇒ SI لكل حجز وبيع الباقة = advance. **قرار Q-B4** |
| خصم مزدوج للساعات | Usage rows تُؤخذ من XStudio ledger فقط (لا يحسب ERP `draw()` للمستورد) + `external_id` على السطر |
| رصيد مدرّس خاطئ | مطابقة يومية `hours_remaining` XStudio vs ERP |
| مركز تكلفة خاطئ | كل موارد XStudio → `استوديو X` فقط؛ test |
| رصيد خزنة خاطئ | PE يدخل `خزينة X Studio`؛ Treasury Close اليومي يكشف الفرق؛ **قاعدة تشغيلية**: الموظف **لا** يسجّل دفعات الاستوديو في ERP يدوياً بعد التفعيل |
| دفعة بتاريخ يوم مُقفَل | `check_closed_days` يرفض → Failed → المحاسب يقرر (reopen أو تاريخ اليوم بملاحظة) |
| دفعة مستقبلية (ساعة الخادم) | `refuse_future_date` → استعمال تاريخ Cairo |

---

## 13. Error Handling and Monitoring (معالجة الأخطاء والمراقبة)

### 13.1 إعادة استعمال `Integration Import Log`

الموجود يغطي: `source_system`, `status` (3 قيم), `started_at/finished_at`, `run_by`, `rows_read`, `inserted`, `records_created`, `skipped`, `changed`, `failed`, `message`, child errors (`row_no`, `external_id`, `kind` = Failed/Changed in Source, `reason`). `file_name/file_hash/file_content` خاصة بالملفات.

**تعديلات مطلوبة (NEW):**

| الحقل | النوع | السبب |
|---|---|---|
| `source_system` option `xstudio` | Select option | حالياً `ba_plus/library_pos/booking`؛ `SOURCE_SYSTEMS` في `.py:21` و`integration_status.py:20` |
| `run_kind` | Select `Incremental/Full/Targeted/Webhook/Reimport` | تمييز التشغيلات |
| `trigger` | Select `Scheduler/Manual/Webhook` | |
| `updated` | Int | حالياً `changed` = "تغيّر في المصدر ولم يُطبَّق"؛ نحتاج عدّاد "طُبِّق التحديث" |
| `unchanged` | Int | = skipped (موجود كـ `skipped`؛ إعادة تسمية label فقط) |
| `duration_seconds` | Float | `finished − started` |
| `entity_counts_json` | Small Text/JSON | عدّادات لكل كيان (bookings/payments/packages/usage/customers) |
| `cursor_before` / `cursor_after` | Data | للتتبع والاستئناف |
| `http_requests`, `http_failures` | Int | |
| child Error: `entity` | Data | أي كيان (`booking/payment/...`) |
| child Error: `kind` options + `Retrying`, `Needs Mapping`, `Changed After Posting`, `Missing In Source` | Select | |
| child Error: `payload_excerpt` | Small Text | JSON مُقنَّع ≤ 500 حرف |

**`XStudio Sync State` (Single, NEW):** `enabled`, `last_attempt_at`, `last_success_at`, `last_full_at`, `consecutive_failures`, `health` Select `Healthy/Degraded/Down/Disabled` (محسوب: Healthy إذا `last_success_at` خلال 2× الفترة؛ Degraded إذا آخر تشغيل Completed with Errors أو retry queue > 0؛ Down إذا 3 فشل متتالٍ)، cursors لكل كيان، `pending_retries` Int.

**تقرير `Integration Status`** (موجود): إضافة صف `xstudio` مع الأعمدة الجديدة (health, duration, retries, next run). ولوحة "XStudio Integration" (Workspace/Page) تعرض آخر 20 تشغيلاً، أخطاء مفتوحة، سجلات needs mapping، وزر "Sync now" (whitelisted، Accounts Manager).

**تنبيهات:** Notification (Frappe) للمحاسب والمالك عند: `health=Down`، أخطاء `Changed After Posting`، صفوف `Needs Mapping` جديدة، فرق مطابقة مالي > 0.

### 13.2 إعادة المحاولة

- HTTP: 3 محاولات بـ backoff داخل التشغيل؛ 5xx/timeout فقط (لا retry على 4xx).
- السجلات: `XStudio Sync Retry` (DocType, NEW): `entity`, `external_id`, `attempts`, `last_error`, `next_attempt_at`, `payload_hash`, `status` (`Pending/Exhausted/Resolved`). يُعاد كل تشغيل؛ بعد 10 محاولات → `Exhausted` + تنبيه. حل الموظف (مثلاً إضافة mapping) ثم "Retry now".

---

## 14. Reconciliation Strategy (استراتيجية المطابقة)

**المبدأ:** المطابقة **تكشف ولا تُصلح**. تُنتِج تقرير `XStudio Reconciliation` (Script Report, NEW) + سجل `XStudio Reconciliation Run` (NEW) يومياً 04:00 بعد الـ full pull، وعند الطلب.

| الفحص | المصدر XStudio | المصدر ERP | قاعدة الفرق | الإجراء |
|---|---|---|---|---|
| R1 عدد الحجوزات لكل يوم/قاعة | `GET /bookings?from&to` (full) | Booking `source_system=xstudio` | id موجود في طرف دون الآخر | Missing in ERP → retry import؛ Missing in source → علَم `missing_in_source` |
| R2 حالة الحجز | `status` | `xstudio_status` | ≠ | سجل + re-sync targeted |
| R3 أوقات الحجز | `starts_at/ends_at` | `xstudio_starts_at/ends_at` | ≠ | نفسه |
| R4 مبالغ الحجز | `price_total, amount_due, amount_paid` | `xstudio_price_total, total_amount, paid_amount` | فرق > 0.01 | نفسه |
| R5 دفعات الحجز | Σ`payments.amount` by booking | Σ`XStudio Payment.amount` by booking؛ (Phase 2) Σ PE `custom_booking` | ≠ | تنبيه محاسب |
| R6 رصيد الباقة | `hours_remaining` | SHP `hours_remaining` (من Usage) | ≠ | تنبيه "manual adjustment in XStudio" + اقتراح سطر تعويضي (يدوي) |
| R7 ledger الباقة | عدد وصفوف `package_usage` | Usage rows بـ `external_id` | id مفقود | import |
| R8 المدفوع على الباقة | Σ`payments` by package | Σ mirror | ≠ | |
| R9 إجمالي التحصيل اليومي | `GET /reports/revenue?granularity=daily` | Σ mirror by posted date؛ (Phase 2) GL `خزينة X Studio` حركة اليوم | ≠ | مقارنة مع Treasury Close `collections` |
| R10 المستحقات | `GET /reports/outstanding` + `unpaid-past` | Booking outstanding للمستورد | ≠ | |
| R11 الإلغاءات والاستردادات | `cancelled` + `method='refund'` | `Cancelled` + mirror سالب | | |
| R12 تكرار مالي | — | PE مكرر لنفس `custom_booking_request`؟ (مستحيل بالـ unique)؛ SI متعددة غير ملغاة لنفس `custom_booking` | > 1 | تنبيه عاجل |
| R13 Needs mapping | `svc:` جديدة، `method` جديد | Service/Payment Method Maps | صف بلا Item/Mode | تنبيه |
| R14 حجوزات يدوية على موارد XStudio | — | Booking `source=Manual` على Resource `managed_by=XStudio` | > 0 | تنبيه (يُمنع لاحقاً) |

**لا كتابة مالية في أي فحص.** الإصلاح يتم إمّا في XStudio (المصدر) ثم re-sync، أو بقيد يدوي في ERP موثَّق.

---

## 15. MVP Scope (النطاق الأدنى)

**الهدف:** كل ما يحدث في XStudio يظهر في ERP خلال 10 دقائق، بشكل **قابل للقراءة والمطابقة**، بدون أي قيد محاسبي آلي.

| البند | التفاصيل |
|---|---|
| **الكيانات** | Customers, Resources (6 قاعات), Bookings (كل الأنواع والحالات), Studio Hour Packages + Usage, Payments (**mirror فقط**), Photographers (master), Week Closings (mirror) |
| **الأحداث** | كل أحداث §10.2 بأثرها "MVP" |
| **مستبعَد** | Payment Entry / Sales Invoice / Journal Entry آلية؛ webhooks؛ مزامنة ERP→XStudio؛ HAL (قاعات Imed)؛ blocks؛ notifications |
| **Endpoints XStudio المطلوبة** | **الحد الأدنى بلا تعديل XStudio**: `GET /halls`, `/config`, `/package-templates`, `/bookings?from&to` (نوافذ 7 أيام للتغلب على حد 500), `/customers?q=` (أحرف a–z/0–9 للتغلب على 200؟ غير موثوق) , `/customers/:id/packages` (N+1), `/photographers`, `/reports/week?start=`, `/admin/export` (مرة واحدة). **الموصى به قبل الإطلاق**: M-00, M-01, M-02, M-03, M-04 (≈ 2–3 أيام عمل لمطوّر XStudio) |
| **تغييرات ERP** | EPIC B كاملاً (حقول + 7 DocTypes جديدة + دور + settings)، EPIC C, D(جزء), E, G(أساس) |
| **الاعتماديات** | حساب تكامل في XStudio؛ URL الإنتاج؛ قرارات Q-B1, Q-B3, Q-B5 (mapping فقط)؛ بيئة staging لـ XStudio (DB منفصلة) |
| **الاختبارات** | unit للـ mappers؛ integration بـ mock server (fixtures JSON من `admin/export` مُنقَّى)؛ idempotency (تشغيل مرتين = لا تغيير)؛ concurrency (حجز يدوي متعارض)؛ contract test ضد staging |
| **المخاطر** | بدون M-01: نافذة 500 صف قد تُفقد حجوزات في أسبوع مزدحم → full pull يومي بنوافذ يوم واحد يحلّها؛ بدون M-03/M-04: تعديلات الباقات/العملاء تُكتشف فقط يومياً |
| **الجهد التقديري** | ERP: 10–14 يوم عمل؛ XStudio: 2–3 أيام؛ QA/UAT: 3 أيام |
| **القيود المتوقعة** | الحجوزات المستوردة read-only؛ لا GL؛ الأرصدة المالية في ERP لا تعكس تحصيل الاستوديو حتى Phase 2 |

## 16. Full Integration Scope (النطاق الكامل)

| البند | إضافة على MVP |
|---|---|
| **Phase 2 — Financial posting** | PE من mirrors (بقواعد §12.2)؛ SI عند completed؛ معالجة الاستردادات؛ تقرير مطابقة GL؛ قفل يومي يتضمن دفعات XStudio |
| **Phase 2 — Webhooks** | M-07 + receiver؛ زمن < 1 دقيقة |
| **Phase 3 — Photographers payout** | JE/Expense من Week Closing؛ حسابات COA جديدة |
| **Phase 3 — Package revenue policy** | SI لبيع الباقة أو deferred |
| **Phase 3 — Reverse sync (اختياري)** | ERP → XStudio: إنشاء عميل/حجز من ERP؟ **غير موصى به** (مصدر حقيقة واحد) |
| **Endpoints إضافية** | M-05, M-06, M-07, F-01..F-06 |
| **تغييرات ERP** | EPIC F كاملاً، تحديث Treasury Close ليشمل مصدر الدفعة، Credit Note للإلغاء بعد الفاتورة |
| **الاختبارات** | مالية: لا PE مكرر، لا SI مكررة، GL يتوازن، Treasury Close يطابق، إلغاء بعد ترحيل |
| **المخاطر** | ازدواج التسجيل اليدوي؛ قرارات محاسبية غير مكتملة؛ أيام مُقفَلة |
| **الجهد** | +10–15 يوم ERP، +3–4 أيام XStudio، +5 أيام UAT محاسبي |

**التوصية: MVP أولاً** لأن (1) يعتمد على ما هو موجود في ERP (`booking_import`, `Import Log`, Imported semantics)، (2) يعطي شهراً من المطابقة الفعلية قبل أي قيد آلي، (3) يكشف فجوات mapping الحقيقية (`svc:`، طرق الدفع، الهواتف) بلا أثر مالي، (4) لا يحتاج قرارات المالك المحاسبية المعلَّقة.

---

## 17. Detailed Epics, Tasks and Subtasks

> القائمة الكاملة بصيغة قابلة للنسخ إلى GitHub Issues في **`XSTUDIO_INTEGRATION_TASKS.md`**. هنا الملخص والترتيب.

| Epic | العنوان | المهام | المالك الرئيسي | المرحلة |
|---|---|---|---|---|
| **A** | XStudio API Preparation | A-01 دور integration + enum؛ A-02 API key؛ A-03 bookings endpoint مع updatedSince/cursor؛ A-04 payments endpoint؛ A-05 updated_at على packages/users + endpoints؛ A-06 package-usage endpoint؛ A-07 customers endpoint؛ A-08 week-closings/photographers؛ A-09 إصلاحات F-01..F-06؛ A-10 openapi.yaml + contract tests؛ A-11 staging environment؛ A-12 webhook emitter (Phase 2) | XStudio Backend | MVP: A-01..A-07, A-11؛ Phase 2: A-08..A-10, A-12 |
| **B** | ERP Data Model Preparation | B-01 حقول تكامل على Customer؛ B-02 حقول على Booking؛ B-03 حقول على Studio Hour Package + Usage؛ B-04 Resource flags؛ B-05 DocTypes mapping (Resource/Service/Payment Method Map)؛ B-06 XStudio Payment mirror؛ B-07 Photographer + Week Closing؛ B-08 Settings + Sync State + Retry؛ B-09 دور ومستخدم؛ B-10 Import Log extensions؛ B-11 seed الموارد الستة | IMED ERP | MVP |
| **C** | Studio Booking Sync | C-01 HTTP client؛ C-02 mappers (time zone/status)؛ C-03 upsert booking مع تحديث المستورد؛ C-04 customer auto-create؛ C-05 initial import؛ C-06 incremental job؛ C-07 cancellations/reschedule/overlap handling؛ C-08 UI (read-only + re-sync) | IMED ERP | MVP |
| **D** | Hall (studio rental) Sync | D-01 mapping hall_rental/location_rental؛ D-02 deposit/price_pending/per_person fields؛ D-03 تقرير إيجار؛ D-04 (Business) قرار قاعات Imed | ERP + Business | MVP (D-01,02)، لاحقاً D-03,04 |
| **E** | Packages & Consumption | E-01 upsert package (submit)؛ E-02 import usage rows؛ E-03 reels unit؛ E-04 expiry؛ E-05 balance reconciliation؛ E-06 deleted packages | IMED ERP | MVP |
| **F** | Payments & Financial | F-01 payment mirror import؛ F-02 payment method map؛ F-03 PE posting (Phase 2)؛ F-04 SI on completed (Phase 2)؛ F-05 refunds؛ F-06 closed-day handling؛ F-07 photographers JE (Phase 3)؛ F-08 package revenue policy | ERP + Business | MVP: F-01, F-02؛ Phase 2+: الباقي |
| **G** | Monitoring, Failures, Recovery | G-01 Import Log fields؛ G-02 Sync State + health؛ G-03 retry queue؛ G-04 Integration Status row + page؛ G-05 notifications؛ G-06 reconciliation report؛ G-07 runbook | IMED ERP | MVP (G-01..G-04, G-06 أساسي) |
| **H** | QA & Deployment | H-01 mock XStudio server fixtures؛ H-02 unit tests mappers؛ H-03 idempotency tests؛ H-04 concurrency tests؛ H-05 contract tests؛ H-06 e2e UAT script؛ H-07 permissions tests؛ H-08 rollout plan (shadow mode → live) ؛ H-09 rollback | Both + DevOps | MVP |

**الترتيب الموصى به:** B-09, B-08 → A-01/A-02/A-11 (بالتوازي) → B-01..B-07, B-10, B-11 → C-01, C-02 → A-03..A-07 → C-03..C-08, E-01..E-04, F-01, F-02, D-01, D-02 → G-01..G-04, G-06 → H-* → shadow run 2 أسابيع → go-live MVP → Phase 2.

---

## 18. Dependencies and Estimated Effort

| المرحلة | ERP (أيام) | XStudio (أيام) | Business/QA (أيام) | الاعتماديات الحرجة |
|---|---|---|---|---|
| تحضير (A-01, A-02, A-11, B-08, B-09) | 2 | 1.5 | 0.5 | وصول لمستودع XStudio ونشر staging؛ `JWT_SECRET` الإنتاج |
| نموذج البيانات (EPIC B) | 3 | — | Q-B1, Q-B3 | |
| API (A-03..A-07) | — | 2 | — | |
| مزامنة الحجوزات والباقات (C, E, D-01/02, F-01/02) | 6 | — | Q-B5 | A-03..A-07 (أو fallback) |
| مراقبة ومطابقة (G) | 2.5 | — | — | |
| QA وإطلاق (H) | 2 | 0.5 | 3 | staging data |
| **MVP إجمالي** | **≈ 15.5** | **≈ 4** | **≈ 3.5** | |
| Phase 2 (F-03..F-06, A-08..A-10, A-12, webhook receiver) | 10–15 | 3–4 | 5 | Q-B2, Q-B4, Q-B5, Q-B7 |

**افتراضات:** مطوّر ERP واحد متفرّغ يعرف Frappe؛ مطوّر XStudio يعرف الكود (ملف routes واحد)؛ staging متاح؛ اليوم = 6 ساعات فعلية.

---

## 19. Risks and Technical Debt

| # | الخطر / الدَّين | الاحتمال | الأثر | التخفيف |
|---|---|---|---|---|
| R-01 | ثلاث نسخ من كود XStudio في المستودع؛ النسخة المنشورة غير مؤكَّدة | عالٍ | تحليل على كود غير مطابق للإنتاج | Q-X1؛ contract test ضد الإنتاج (`/api/health`, `/api/config`) |
| R-02 | XStudio بلا pagination/updatedSince → اعتماد على نوافذ زمنية وحد 500 | عالٍ | فقد حجوزات | A-03 قبل الإطلاق؛ full pull يومي بنوافذ يوم |
| R-03 | تعديلات صامتة للباقات/العملاء (لا updated_at) | متوسط | رصيد خاطئ | A-05 + R6 |
| R-04 | حذف فعلي للباقات في XStudio | متوسط | فقد ledger | Q-X5 soft delete |
| R-05 | دلالة الحالة `confirmed` vs `Confirmed with Deposit` | مؤكَّد | تقارير ERP تُظهر "Tentative" لحجوزات مؤكدة | حفظ `xstudio_status`؛ تعديل list view |
| R-06 | الحجز اليدوي في ERP على موارد XStudio | متوسط | رفض استيراد (Already Booked) | B-04 منع |
| R-07 | الازدواج اليدوي للدفعات بعد Phase 2 | عالٍ | خزنة لا تطابق | قاعدة تشغيلية + تدريب + R9 |
| R-08 | التوكن 7 أيام | مؤكَّد | انقطاع أسبوعي | A-02 API key |
| R-09 | XStudio على Railway/Supabase free tier؛ timers داخل العملية | متوسط | توفر | health check + retries |
| R-10 | `svc:` ديناميكية بلا Item | متوسط | حجوزات بلا تصنيف | Needs Mapping queue |
| R-11 | أسعار مختلفة بين النظامين (`STU-PODCAST-*`) | مؤكَّد | التباس في التقارير | XStudio مصدر السعر؛ تعطيل التسعير للمستورد (موجود) |
| R-12 | حجوزات تعبر منتصف الليل | منخفض | Failed rows | 23:59:59 + علم |
| R-13 | Import Log Select محدود | مؤكَّد | لا سجل لـ xstudio | B-10 |
| R-14 | لا HTTP client/credentials في ERP (أول تكامل خارجي) | مؤكَّد | جهد تأسيسي | EPIC B-08, C-01 |
| R-15 | قرارات محاسبية معلَّقة (revenue timing، مصورون، قاعات) | عالٍ | يؤخر Phase 2 | MVP لا يعتمد عليها |
| R-16 | `viewer`/`integration` غير موجودة في enum | مؤكَّد | إنشاء المستخدم يفشل | A-01 |
| R-17 | ERP `refuse_future_date` + Treasury Close closed days | متوسط | Failed PEs | F-06 |

---

## 20. Questions for the XStudio Developer

| ID | السؤال |
|---|---|
| Q-X1 | أي نسخة منشورة فعلياً على xstudioeg.com: `xstudio-platform/backend/src/` أم الملفات المفردة في `xstudio-platform/` (الأحدث)؟ وما commit الإنتاج؟ |
| Q-X2 | هل `JWT_SECRET`, `DATABASE_URL`, `TZ=Africa/Cairo` مضبوطة في الإنتاج؟ (لا نحتاج القيم، فقط التأكيد.) |
| Q-X3 | هل يمكن نشر بيئة staging (Railway service + Supabase project منفصلان) بنسخة من بيانات الإنتاج مُقنَّعة الهواتف؟ |
| Q-X4 | الموافقة على M-00 (دور `integration` + API key) و M-01..M-04 وجدولها الزمني. |
| Q-X5 | تحويل `DELETE /customer-packages/:id` إلى soft delete أو تسجيل سطر ledger؛ وإضافة `updated_at` إلى `customer_packages` و`users`. |
| Q-X6 | هل يوجد deep link لحجز بعينه في `admin.html` (مثلاً `#booking=<id>`)؟ إن لا، هل يمكن إضافته؟ |
| Q-X7 | قيم `payments.method` الفعلية المستعملة في الإنتاج (الكود: `cash, transfer, instapay, other, refund`؛ الواجهة: `cash, transfer, instapay`). هل يوجد `card`/`vodafone`؟ |
| Q-X8 | ما العلاقة بين `price_total` و`amount_due` عند `settle=true`؟ هل يُقبل تسجيل الخصم كسطر صريح (F-03)؟ |
| Q-X9 | هل تُستعمل `users.email` فعلياً للعملاء؟ هل نُزامنها؟ |
| Q-X10 | هل سيُدمج فرع `half-hour-booking`؟ (يؤثر على `hours` بكسور 0.5 — مدعوم في ERP.) |
| Q-X11 | حجم البيانات الحالي: عدد الحجوزات/العملاء/الباقات/الدفعات (لتقدير الاستيراد الأولي). |
| Q-X12 | هل الحجز قد يعبر منتصف الليل فعلياً في الإنتاج (`close_minute=1440`)؟ |
| Q-X13 | هل يمكن تمرير `people`/`perPerson` إلى أعمدة (F-04) وهل تُستعمل `per_person` فعلاً؟ |
| Q-X14 | جدول نسخ الاحتياط والـ retention للـ `audit_logs` (إن اعتمدنا M-06). |

## 21. Questions for the IMED Business Owner

| ID | السؤال | يؤثر على |
|---|---|---|
| Q-B1 | عميل XStudio غير موجود في ERP: يُنشأ تلقائياً؟ بأي Customer Group (`مدرّس` جديدة؟)؛ والعميل بلا هاتف؟ | C-04, B-01 |
| Q-B2 | هل تُنشأ Sales Invoice آلياً لكل حجز استوديو مكتمل؟ بتاريخ الجلسة؟ وماذا عن الحجز المغطى كلياً بباقة (0 جنيه)؟ | F-04 |
| Q-B3 | حجز حتى 24:00 بالضبط: يُسجَّل في ERP حتى 23:59:59؟ | C-02 |
| Q-B4 | إيراد الباقة: يُعترف به عند البيع (فاتورة الباقة) أم عند الاستهلاك (فاتورة كل جلسة)؟ (معلَّق في `v1.3-amendments.md:93`) | F-04, F-08 |
| Q-B5 | خريطة طرق الدفع: `cash → نقدي — استوديو X` ✔؛ `instapay → InstaPay` ✔؛ `transfer` → أي حساب بنكي؟ (لا حساب بنك في COA سوى المحافظ)؛ `other` → ؟؛ الاسترداد يخرج من أي خزنة؟ | F-02 |
| Q-B6 | هل قاعات Imed (المحاضرات) ستُدار في XStudio مستقبلاً أم تبقى يدوية في ERP؟ | D-04 |
| Q-B7 | نسب المصورين: تُسجَّل في ERP كمصروف مستحق للمصورين (Employee أم Supplier)؟ بأي حساب؟ تُدفع من `خزينة X Studio`؟ | F-07, B-07 |
| Q-B8 | بعد تفعيل Phase 2: هل يتوقف الموظف عن تسجيل دفعات الاستوديو في ERP يدوياً (مصدر واحد)؟ | F-03 |
| Q-B9 | تعديل في XStudio على حجز له فاتورة في ERP: من يراجع؟ المحاسب يُعدِّل يدوياً أم يُعاد الحجز إلى XStudio؟ | B7 (§7) |
| Q-B10 | التعديلات اليدوية على رصيد الباقة في XStudio: تُنسخ إلى ERP كسطر تعويضي تلقائياً أم تنبيه فقط؟ | E-05 |
| Q-B11 | `price_pending`: يُستثنى من التقارير المالية حتى يُحدَّد السعر؟ | D-02 |
| Q-B12 | هل الموارد الحالية في ERP (`سمارت بورد 86 بوصة`, `ريلز`, `بودكاست`…) تُعطَّل بعد التكامل أم تبقى للحجز اليدوي الطارئ؟ | B-11 |
| Q-B13 | من يملك حساب `integration` في XStudio ومن يحتفظ بالمفتاح؟ | B-08, A-02 |

## 22. Recommended Next Steps

1. **مراجعة هذه الوثيقة** مع مطوّر XStudio والمالك؛ الإجابة على Q-X1..X5 وQ-B1, Q-B3, Q-B5 (كافية لبدء MVP).
2. **XStudio**: نشر staging (A-11)، تنفيذ A-01, A-02 (نصف يوم)، ثم A-03..A-07.
3. **ERP**: البدء بـ EPIC B (لا يعتمد على XStudio) وC-01/C-02 مع mock server من fixtures.
4. **Shadow run** أسبوعين: المزامنة تعمل على الإنتاج بدون أي ترحيل مالي؛ المحاسب يقارن تقرير المطابقة يومياً.
5. **Go-live MVP**، ثم اجتماع قرارات Phase 2 (Q-B2, Q-B4, Q-B7, Q-B8).
6. **Phase 2**: الترحيل المالي تدريجياً (PE أولاً، ثم SI)، ثم webhooks.

> **ملاحظة:** لم يُنفَّذ أي كود. كل ما سبق مقترح للمراجعة.
