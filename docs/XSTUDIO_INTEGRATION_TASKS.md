# XStudio × IMED ERP — Integration Task Backlog

> قائمة مهام قابلة للتحويل مباشرة إلى GitHub Issues. مرجع التحليل: `docs/XSTUDIO_ERP_INTEGRATION_ANALYSIS.md`.
> **لا شيء من هذا مُنفَّذ.** كل مهمة: ID · Epic · Title · Objective · Existing · Change · Files · Owner · Priority · Depends · Effort (ساعات، مطوّر يعرف الكود) · Acceptance · Tests · Risks · DoD.
> مسارات XStudio نسبية إلى `xstudio-platform/`؛ مسارات ERP نسبية إلى `apps/imed_erp/imed_erp/` (مختصر `APP/`).
> **تصنيف الملكية:** 🟦 ERP فقط · 🟩 XStudio فقط · 🟨 كلاهما · 🟪 يحتاج وصول/نشر · 🟥 قرار عمل.

---

## EPIC A — XStudio API Preparation (🟩 XStudio Backend)

### A-01 · دور `integration` + إصلاح enum `user_role`
- **Objective:** حساب قراءة-فقط للـ ERP لا يملك أي صلاحية كتابة.
- **Existing:** `backend/src/middleware/auth.js:7-27` PERMS بدون دور قراءة شامل؛ `viewer` مستعمل في الكود لكنه غائب من `schema.sql:12`.
- **Change:** إضافة `integration: ["bookings.read","halls.read","customers.read","packages.read","payments.read","reports.read","integration.read"]`; في `backend/src/index.js:ensureSchema()` إضافة `ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'viewer'` و`'integration'`; السماح بالدور في `routes.js:708,740` (قوائم الأدوار المسموحة) و`routes.js:38 STAFF` (لا يُضاف إلى STAFF حتى لا يُعامَل كموظف في cancel/reschedule).
- **Owner:** XStudio Backend · **Priority:** P0 · **Depends:** — · **Effort:** 3h
- **Acceptance:** مستخدم بدور integration يحصل 200 على GET bookings/customers/packages/reports و403 على أي POST/PATCH/DELETE.
- **Tests:** test جديد في `backend/test/api.test.js` (RBAC matrix للدور).
- **Risks:** `ALTER TYPE … ADD VALUE` لا يعمل داخل transaction في Postgres القديمة؛ `ensureSchema` يُشغِّل كل statement منفرداً ✅.
- **DoD:** مدموج، منشور على staging، موثَّق في `docs/api.md` (role matrix).

### A-02 · API key طويل الأمد (`X-Api-Key`)
- **Objective:** إزالة الحاجة لتخزين كلمة سر وتجديد JWT كل 7 أيام.
- **Existing:** `authRequired` يقبل Bearer JWT فقط (`auth.js:34-44`)؛ `jwtExpiry: "7d"` (`db.js:7`).
- **Change:** جدول `api_keys (id uuid, user_id, key_hash text, label, created_at, last_used_at, revoked_at)` في `ensureSchema()`; في `authRequired` إن وُجد header `X-Api-Key` → `sha256` ومطابقة → `req.user` من `users`; endpoint `POST /api/admin/api-keys` و`DELETE /api/admin/api-keys/:id` (super_admin) يُرجع المفتاح مرة واحدة فقط؛ audit `api_key.create/revoke`.
- **Owner:** XStudio Backend · **Priority:** P0 · **Depends:** A-01 · **Effort:** 5h
- **Acceptance:** طلب بـ `X-Api-Key` صالح = 200؛ مُبطَل = 401؛ المفتاح لا يُخزَّن نصاً.
- **Tests:** إنشاء/استعمال/إبطال؛ المفتاح غير مرئي في `GET /admin/export`.
- **Risks:** تسريب المفتاح؛ يُعالَج بالإبطال.
- **DoD:** مدموج + موثَّق + مفتاح staging مُسلَّم لفريق ERP عبر قناة آمنة (ليس في git/Trello).

### A-03 · `GET /api/integration/bookings?updatedSince&cursor&limit`
- **Objective:** مزامنة تزايدية للحجوزات مع دفعاتها وledger باقاتها.
- **Existing:** `GET /api/bookings` (`routes.js:569-584`) LIMIT 500، فلتر على `starts_at` فقط، لا `updated_at`.
- **Change:** ملف جديد `backend/src/routes/integration.js` (أو قسم في `routes.js`) بالعقد الموصوف في التحليل §5 M-01؛ `requirePerm("integration.read")`; cursor = base64(`updated_at|id`); `ORDER BY updated_at, id`; `LEFT JOIN LATERAL` لتجميع `payments` و`package_usage` كـ JSON؛ index `bookings_updated_idx (updated_at, id)` في `ensureSchema()`; `serverTime` في الاستجابة.
- **Owner:** XStudio Backend · **Priority:** P0 · **Depends:** A-01 · **Effort:** 8h
- **Acceptance:** صفحات متتالية لا تُسقِط ولا تُكرّر سجلاً حتى مع تحديثات متزامنة (overlap بـ `>=` + id)؛ `limit` 1..1000؛ 422 لقيم غير صالحة.
- **Tests:** 3 حجوزات، تحديث الوسطى، `updatedSince` يُرجعها فقط؛ pagination بـ limit=1.
- **Risks:** تجميع JSON على 1000 صف ثقيل → cap 1000.
- **DoD:** مدموج، `docs/openapi.yaml` (A-10) محدَّث، staging.

### A-04 · `GET /api/integration/payments?since&cursor&limit`
- **Objective:** قراءة سجل الدفعات بمعرّفاته (أساس أي Payment Entry).
- **Existing:** لا endpoint؛ `payments` تُرجع بدون `id` في `GET /customers/:id/packages` (`routes.js:912-914`).
- **Change:** endpoint على `payments ⟕ bookings ⟕ customer_packages ⟕ users(recorded_by)`؛ `since` على `created_at`؛ index `payments_created_idx (created_at, id)`.
- **Owner:** XStudio Backend · **Priority:** P0 · **Depends:** A-01 · **Effort:** 4h
- **Acceptance:** كل سطر يحمل `id, booking_id, package_id, customer_id, amount, method, recorded_by, recorded_by_name, created_at`.
- **Tests:** دفعة حجز + دفعة باقة + استرداد سالب تظهر الثلاث.
- **DoD:** مدموج + staging.

### A-05 · `updated_at` على `customer_packages` و`users` + endpoints قراءة
- **Objective:** كشف التعديلات اليدوية للباقات والعملاء.
- **Existing:** لا `updated_at` على الجدولين (`schema.sql:24-35, 64-75`); `PATCH /customer-packages/:id` (`routes.js:825-845`) يعدّل بصمت.
- **Change:** `ensureSchema()`: `ALTER TABLE customer_packages ADD COLUMN IF NOT EXISTS updated_at timestamptz NOT NULL DEFAULT now()` + trigger `set_updated_at` (الدالة موجودة `schema.sql:168-170`)؛ نفسه لـ `users`; endpoints `GET /api/integration/customer-packages?updatedSince` (مع `template_category`, `unit`) و`GET /api/integration/customers?updatedSince` (بدون password_hash).
- **Owner:** XStudio Backend · **Priority:** P0 · **Depends:** A-01 · **Effort:** 6h
- **Acceptance:** PATCH على باقة يغيّر `updated_at`؛ endpoint يُرجعها بـ `updatedSince`.
- **Tests:** trigger + endpoint.
- **Risks:** `UPDATE customer_packages SET hours_remaining…` داخل createBooking يحدّث `updated_at` أيضاً (مرغوب).
- **DoD:** مدموج + staging.

### A-06 · `GET /api/integration/package-usage?since&cursor&limit`
- **Objective:** ledger الاستهلاك مستقلاً (append-only).
- **Existing:** يظهر فقط داخل `GET /customers/:id/packages` (`routes.js:915`).
- **Change:** endpoint على `package_usage` بـ `created_at` cursor؛ index.
- **Owner:** XStudio Backend · **Priority:** P1 (P0 إن لم يُدمَج داخل A-03) · **Depends:** A-01 · **Effort:** 2h
- **Acceptance/Tests:** خصم + استرداد يظهران بإشارتيهما.
- **DoD:** مدموج.

### A-07 · `GET /api/integration/photographers` + `GET /api/integration/week-closings?since`
- **Objective:** مرآة نسب المصورين في ERP.
- **Existing:** `GET /photographers` (bookings.read) و`GET /reports/week?start=` لأسبوع واحد (`routes.js:1065-1157`).
- **Change:** endpoint يُرجع كل `week_closings` بـ `closed_at >= since` مع `data` كاملة + اسم المُقفِل.
- **Owner:** XStudio Backend · **Priority:** P1 · **Depends:** A-01 · **Effort:** 2h
- **DoD:** مدموج.

### A-08 · إصلاحات سلامة البيانات (F-01..F-06)
- **Objective:** إغلاق الثغرات التي تُفسد التكامل.
- **Existing/Change:**
  - F-01 `POST /bookings/:id/complete` (`routes.js:666-673`): رفض إن `status='cancelled'`؛ تحذير إن `completed` مسبقاً.
  - F-02 `PATCH /customer-packages/:id` (`routes.js:825-845`): عند تغيير `hoursRemaining` كتابة سطر `package_usage reason='manual_adjust'` بالفرق، داخل transaction.
  - F-03 `POST /bookings/:id/pay` مع `settle=true` (`routes.js:545-549`): عمود `discount_amount` على `bookings` = `price_total − amount_due` أو سطر payments `method='discount'`.
  - F-04 `pricing.mode='per_person'`: أعمدة `people int`, `per_person numeric` على `bookings` (`bookingService.js:217-219`).
  - F-05 soft delete للباقات: `deleted_at` بدل `DELETE` (`routes.js:865-878`)؛ الاستعلامات تستثني المحذوف.
  - F-06 `GET /admin/export` يستثني `password_hash` (`routes.js:98-104`).
- **Owner:** XStudio Backend · **Priority:** P1 (F-05, F-02 P1؛ الباقي P2) · **Depends:** — · **Effort:** 8h
- **Tests:** واحد لكل إصلاح.
- **Risks:** F-05 يغيّر سلوك الواجهة (الباقة المحذوفة تختفي من القوائم → فلتر).
- **DoD:** مدموج.

### A-09 · `docs/openapi.yaml` + contract tests
- **Objective:** عقد ثابت بين النظامين.
- **Existing:** `docs/api.md` يدوي وقديم (cancel 12h vs 24h في `db.js:10`؛ endpoints كثيرة غير مذكورة).
- **Change:** OpenAPI 3.1 لـ `/api/integration/*` + `/api/health` + `/api/config` + `/api/halls`؛ test `backend/test/integration-api.test.js` يتحقق بالـ schema (ajv).
- **Owner:** XStudio Backend · **Priority:** P1 · **Depends:** A-03..A-07 · **Effort:** 5h
- **DoD:** الـ CI يفشل عند كسر العقد؛ نسخة في ERP `docs/integrations/xstudio/openapi.yaml`.

### A-10 · بيئة Staging لـ XStudio 🟪
- **Objective:** تطوير واختبار بلا لمس الإنتاج.
- **Change:** Railway service + Supabase project منفصلان، `WHATSAPP_DRIVER=dev`, بدون `TELEGRAM_*`، بيانات إنتاج مُقنَّعة (هواتف وأسماء) عبر script `scripts/anonymise.sql` (جديد).
- **Owner:** XStudio Backend + DevOps · **Priority:** P0 · **Effort:** 4h
- **DoD:** URL staging + API key للـ ERP.

### A-11 · Webhook emitter (Phase 2)
- **Objective:** زمن ظهور < دقيقة.
- **Change:** `backend/src/services/webhooks.js`: `emit(event, entity, id, data)` بعد commit في `routes.js` (create/confirm/pay/amount-due/cancel/reschedule/apply-package/complete/photographer, packages, payments, week close); جدول `webhook_deliveries`; HMAC-SHA256؛ retry backoff (timers كما في `index.js:110-114`); settings `WEBHOOK_URL`, `WEBHOOK_SECRET`.
- **Owner:** XStudio Backend · **Priority:** P2 · **Depends:** A-03 (نفس الـ payload shape) · **Effort:** 10h
- **Tests:** توقيع صحيح؛ retry عند 500؛ idempotent delivery id.
- **DoD:** staging يرسل إلى ERP staging.

### A-12 · توضيح النسخة المنشورة وتنظيف المكرَّرات 🟥/🟩
- **Objective:** مصدر حقيقة واحد للكود.
- **Existing:** 3 نسخ (الجذر، `xstudio-platform/backend/src`, ملفات مفردة في `xstudio-platform/`) + `backend/src/bookingService.js` القديم.
- **Change:** تأكيد commit الإنتاج (Q-X1)؛ حذف/دمج النسخ الطائشة؛ تحديث `OLD-CODE.md`.
- **Owner:** XStudio Backend · **Priority:** P1 · **Effort:** 2h

---

## EPIC B — ERP Data Model Preparation (🟦 IMED ERP)

### B-01 · حقول تكامل على `Customer`
- **Existing:** `APP/imederp/customers.py:41-68` custom fields (`custom_phone_key`…); لا external id.
- **Change:** Custom Fields: `xstudio_customer_id` Data unique read_only, `xstudio_source_updated_at` Datetime, `xstudio_last_synced_at` Datetime (تُنشأ في `make_custom_fields()` جديد `APP/integrations/xstudio/fields.py` وتُستدعى من `hooks.py after_install/after_migrate`).
- **Priority:** P0 · **Effort:** 2h · **Tests:** unique؛ migrate idempotent.
- **DoD:** الحقول تظهر في Customer (قسم "XStudio") read-only.

### B-02 · حقول إضافية على `Booking`
- **Existing:** `booking.json` فيه `source/source_system/external_id/import_key`.
- **Change:** حقول read_only no_copy: `source_updated_at` Datetime, `last_synced_at` Datetime, `import_log` Link, `source_payload_hash` Data, `xstudio_status` Select, `xstudio_payment_status` Select, `xstudio_booking_type` Data, `xstudio_service_item` Link Item, `xstudio_screen_size` Int, `xstudio_cameras` Int, `xstudio_price_total` Currency, `xstudio_discount_amount` Currency, `price_pending` Check, `deposit_due` Currency, `xstudio_starts_at` Datetime, `xstudio_ends_at` Datetime, `xstudio_customer_name` Data, `xstudio_customer_phone` Data, `xstudio_photographer` Link, `xstudio_created_at` Datetime. قسم "Source" يُوسَّع. `booking_list.js` يعرض `xstudio_status` للمستورد.
- **Files:** `APP/imederp/doctype/booking/booking.json`, `booking.js`, `booking_list.js`
- **Priority:** P0 · **Effort:** 4h · **Tests:** `test_booking.py` manual source يمسح الحقول الجديدة؛ imported يحفظها.
- **Risks:** تضخم الفورم → collapsible section.

### B-03 · حقول تكامل على `Studio Hour Package` + `Studio Hour Package Usage`
- **Existing:** لا source fields، لا expiry (`studio_hour_package.json`).
- **Change:** SHP: `source` Select, `source_system`, `external_id`, `import_key` unique, `source_updated_at`, `last_synced_at`, `import_log`, `expires_on` Date, `unit` Select `Hour|Reel` default Hour, `xstudio_category` Data, `xstudio_template_id` Data, `xstudio_payment_status` Select, `package_name` Data. Usage child: `external_id` Data, `source_reason` Data. تعديل `studio_hour_package.py validate` ليقبل `flags.from_import` (Resource تجميعي، قبول status حسب الرصيد) و`record()` ليقبل `external_id` ويرفض التكرار.
- **Priority:** P0 · **Effort:** 6h · **Tests:** استيراد باقة مرتين = سطر واحد؛ usage مكرر مرفوض؛ reels unit لا يُحسب كساعات في التقارير.

### B-04 · `Booking Resource` — إدارة خارجية
- **Change:** حقول `managed_by_source` Select `""|XStudio`, `xstudio_hall_id` Int unique. في `booking.py check_resource`: إذا Resource `managed_by_source` وليس `flags.from_import` → throw "This resource is booked in XStudio".
- **Priority:** P1 · **Effort:** 2h · **Tests:** حجز يدوي مرفوض؛ مستورد مقبول.
- **Business:** Q-B12.

### B-05 · DocTypes mapping: `XStudio Resource Map`, `XStudio Service Map`, `XStudio Payment Method Map`
- **Change:** `XStudio Resource Map` (hall_id Int unique, resource Link); `XStudio Service Map` (service_key Data unique مثل `smartboard:86`, `podcast:2`, `svc:abc#1`; title Data; item Link Item; status `Mapped|Needs Mapping`); `XStudio Payment Method Map` (method Data unique; mode_of_payment Link; status). الصفوف تُضاف تلقائياً بـ Needs Mapping عند ظهور قيمة جديدة. Perms: Accounts Manager write.
- **Priority:** P0 · **Effort:** 4h · **Tests:** قيمة جديدة تُنشئ صف Needs Mapping ولا تُفشِل الحجز.

### B-06 · DocType `XStudio Payment` (mirror)
- **Change:** حقول: `external_id` unique, `import_key`, `booking` Link, `hour_package` Link, `customer` Link, `amount` Currency (موجب/سالب), `direction` Select `Receive|Refund|Discount`, `method` Data, `mode_of_payment` Link (من الmap), `recorded_by_name`, `posted_at` Datetime, `posting_date` Date, `status` Select `Mirrored|Posted|Skipped|Failed|Needs Mapping`, `payment_entry` Link, `fail_reason`, `source_updated_at`, `last_synced_at`, `import_log`. not submittable; read-only في الواجهة؛ `on_trash` ممنوع (`no_delete`). Perms: Accounts Manager read؛ Integration Runner create/write.
- **Priority:** P0 · **Effort:** 3h · **Tests:** تكرار مرفوض بالـ unique.

### B-07 · DocTypes `XStudio Photographer`, `XStudio Week Closing` (+ child `XStudio Week Closing Line`)
- **Change:** Photographer: `external_id` unique, `photographer_name`, `disabled`, `employee` Link Employee (اختياري), `supplier` Link (اختياري). Week Closing: `week_start` Date unique, `closed_at`, `closed_by_name`, `base` Select `paid|price`, `total_cut` Currency, `totals_json` Small Text, `notes`, lines (photographer Link, bucket Data, bucket_label, count Int, amount, pct Percent, cut Currency), `journal_entry` Link ro, source fields.
- **Priority:** P1 · **Effort:** 3h

### B-08 · `XStudio Settings` (Single) + `XStudio Sync State` (Single) + `XStudio Sync Retry`
- **Change:** Settings: `enabled` Check, `base_url` Data (https only), `auth_mode` Select `API Key|Password`, `api_key` Password, `username` Data, `password` Password, `poll_minutes` Int default 10, `overlap_minutes` Int default 5, `page_size` Int default 500, `default_customer_group` Link, `packages_resource` Link Booking Resource, `webhook_secret` Password, `notify_users` Table MultiSelect. Sync State: cursors (bookings/payments/packages/usage/customers/week_closings) Data, `last_attempt_at`, `last_success_at`, `last_full_at`, `consecutive_failures` Int, `health` Select, `pending_retries` Int. Retry: `entity`, `external_id`, `attempts`, `last_error`, `next_attempt_at`, `status`. Perms: System Manager فقط للـ Settings.
- **Priority:** P0 · **Effort:** 4h · **Tests:** رفض `http://`؛ الأسرار لا تظهر في `frappe.get_doc(...).as_dict()` للمستخدم غير المخوَّل.

### B-09 · دور `Integration Runner` + مستخدم `integration-xstudio`
- **Existing:** `APP/setup/setup_users.py:37,81-102` لا مستخدم تكاملي؛ `IMPORT_DATA_STANDARD.md:24` يطلب واحداً لكل نظام.
- **Change:** دور جديد؛ صلاحيات create/write/read على Booking, Customer, Studio Hour Package, XStudio *; read على Item/Booking Resource/Mode of Payment; User Permission Cost Center `استوديو X - MMG`; المستخدم بلا login (API only, `enabled` + `user_type=System User`, كلمة سر عشوائية). `sync.py` يستعمل `frappe.set_user()` عليه.
- **Priority:** P0 · **Effort:** 3h · **Tests:** `test_permissions`: المستخدم لا يقرأ Booking لمركز `قاعات Imed`.

### B-10 · توسيع `Integration Import Log`
- **Existing:** `integration_import_log.{json,py}`; `SOURCE_SYSTEMS` (py:21); `integration_status.py:20`.
- **Change:** option `xstudio` في `source_system` + `SOURCE_SYSTEMS` + labels؛ حقول `run_kind`, `trigger`, `updated`, `duration_seconds`, `entity_counts_json`, `cursor_before`, `cursor_after`, `http_requests`, `http_failures`; child: `entity`, `payload_excerpt`, `kind` options جديدة. `ImportRun.updated()` و`ImportRun.counts(entity, …)`.
- **Priority:** P0 · **Effort:** 4h · **Tests:** `test_app_import.py` لا ينكسر؛ test جديد للعدّادات.

### B-11 · Seed الموارد والـ Items
- **Change:** `APP/setup/setup_xstudio.py` (جديد، idempotent): 6 Booking Resources `X Studio — Hall {1,3,4,5,6,8}` (Studio Service, `استوديو X`, item `STUDIO-HOUR`, `managed_by_source=XStudio`, `xstudio_hall_id`), Resource `X Studio — Packages`; Items جديدة `STU-SB86-HOUR`, `STU-LOCATION-HOUR`, `STU-HALL-RENTAL-HOUR`; Resource Map 6 صفوف؛ Service Map الافتراضية (session, smartboard:75/86, podcast:1/2/3, reels, hall_rental, location_rental)؛ Payment Method Map (`cash→نقدي — استوديو X`, `instapay→InstaPay`; `transfer/other` Needs Mapping حتى Q-B5). **لا يُشغَّل على الإنتاج قبل المراجعة.**
- **Priority:** P0 · **Effort:** 3h · **Business:** Q-B5, Q-B12.

---

## EPIC C — Studio Booking Synchronization (🟦 IMED ERP)

### C-01 · HTTP client `APP/integrations/xstudio/client.py`
- **Existing:** لا outbound HTTP في ERP (grep `requests.` فارغ).
- **Change:** `XStudioClient(settings)`: `get(path, params)` مع timeout 15s، retry 3× backoff على 5xx/timeout، header `X-Api-Key` أو Bearer مع تجديد تلقائي عند 401 (مرة واحدة)، `iterate(path, cursor_key, since)` generator للصفحات، عدّادات `requests/failures`، إخفاء الأسرار في logs، `health()`.
- **Priority:** P0 · **Effort:** 6h · **Tests:** بـ `responses`/`unittest.mock`: retry، 401→refresh، pagination.
- **Risks:** `requests` متاح في Frappe ✅.

### C-02 · Mappers (pure functions) `mappers/bookings.py`, `mappers/common.py`
- **Change:** `to_local(dt_utc) → (date, time)` بـ `zoneinfo("Africa/Cairo")`؛ `ends_at` منتصف الليل → `23:59:59` + علم؛ `map_status(status, amount_paid) → ERP status`؛ `service_key(booking)`؛ `cancellation_reason(b)`؛ `payload_hash(b)`؛ `booking_values(b, resource, customer, item)` بالشكل الذي يتوقعه `booking_import.booking_values` الحالي (توسيعه بدل تكراره).
- **Priority:** P0 · **Effort:** 5h · **Tests:** جدول حالات §8.5 كاملاً؛ 24:00؛ price_pending؛ `amount_paid > amount_due`.

### C-03 · Upsert الحجز مع **تحديث** المستورد
- **Existing:** `booking_import.import_bookings` يُدرج الجديد ويُعلِّم المتغيّر "changed" **بلا تحديث** (`booking_import.py:43-48`)؛ `booking.check_source` يرفض حفظ المستورد (`booking.py:139-143`).
- **Change:** في `check_source`: السماح بالحفظ إذا `self.flags.from_import` حتى للمستورد الموجود؛ رفض إذا `source_updated_at` الوارد أقدم من المخزَّن؛ `writers/bookings.py upsert_booking(values)`: إن موجود ومتطابق hash → `skipped`; إن مختلف → `doc.update(values); doc.flags.from_import=True; doc.save()` → `updated`; إن للحجز `sales_invoice/journal_entry` مرحَّل → لا حفظ، سجل `Changed After Posting`. `check_hour_package` (`booking.py:102-103`) يسمح بالباقة للمستورد إذا `from_import`. `check_overlap` يبقى.
- **Priority:** P0 · **Effort:** 8h · **Tests:** تعديل `test_booking.py:281` ("imported booking changed only in source") ليعكس السياسة الجديدة؛ تحديث أقدم مرفوض؛ overlap مع يدوي → Failed بسبب واضح؛ posted → Changed After Posting.
- **Risks:** تغيير سياسة INT-01 الموثَّقة → يحتاج موافقة (Q-B9).

### C-04 · إنشاء/ربط العميل تلقائياً
- **Existing:** `booking_import.booking_values` يفشل إن الهاتف غير معروف (`booking_import.py:73-78`); BA Plus ينشئ الطالب (`app_import.py:238-249`).
- **Change:** `writers/customers.py upsert_customer(x)`: lookup بـ `xstudio_customer_id` → وإلا `customer_with_phone(normalize_phone)` وربط → وإلا إنشاء Customer (`customer_group` من Settings, `customer_type=Individual`, `mobile_no`)؛ placeholder `no-phone-*` → بلا هاتف؛ تعارض هاتف مع عميل له id آخر → Failed.
- **Priority:** P0 · **Effort:** 5h · **Tests:** الثلاث حالات + تعارض.
- **Business:** Q-B1.

### C-05 · الاستيراد الأولي (initial import)
- **Change:** `sync.run_full(from_scratch=True)` بالترتيب halls→customers→packages→bookings→usage→payments→photographers→week_closings بصفحات؛ أو شاشة "Import XStudio Snapshot" ترفع JSON من `GET /admin/export` (بعد تنقية) وتُغذّي نفس writers. Dry-run mode يُنتج تقرير "ماذا سيُنشأ" بلا كتابة.
- **Priority:** P0 · **Depends:** A-03..A-07 أو snapshot · **Effort:** 6h · **Tests:** fixture 50 حجز/10 عملاء/5 باقات → أعداد صحيحة؛ تشغيل ثانٍ = كلها skipped.
- **Risks:** حجم البيانات (Q-X11)؛ تعارضات مع حجوزات يدوية قائمة في ERP على نفس الموارد (تقرير قبل التشغيل).

### C-06 · Scheduler incremental + Sync State
- **Change:** `hooks.py scheduler_events cron "*/10 * * * *" → sync.run_incremental` (يتحقق `enabled` و`consecutive_failures < N`), `"30 3 * * *" → sync.run_full`; تحديث cursors بعد كل صفحة؛ `ImportRun` لكل تشغيل؛ lock عبر `frappe.cache().lock("xstudio_sync")` لمنع التداخل.
- **Priority:** P0 · **Effort:** 5h · **Tests:** تشغيلان متزامنان → الثاني يخرج؛ cursor يتقدم فقط عند النجاح.

### C-07 · الإلغاء، النقل، التعارض، 24:00
- **Change:** في `upsert_booking`: cancelled → `status=Cancelled` + reason؛ reschedule → تحديث الأوقات ثم `check_overlap`; تعارض مع يدوي → Failed + Retry queue + تنبيه؛ عبور منتصف الليل → `23:59:59` + علم أو Failed حسب Q-B3.
- **Priority:** P0 · **Effort:** 4h (ضمن C-03 جزئياً) · **Tests:** لكل سيناريو.

### C-08 · واجهة ERP للحجز المستورد
- **Existing:** `booking.js:42-52` يعطّل الفورم للمستورد.
- **Change:** عرض بطاقة "XStudio" (الحالة الأصلية، نوع الخدمة، المدفوع، آخر مزامنة)؛ زر "Re-sync from XStudio" (whitelisted `sync.run_targeted`, Accounts Manager/Branch Manager)؛ إخفاء أزرار الدفع/الإكمال؛ list view: عمود `xstudio_status`؛ تقويم: لون مميّز للمستورد.
- **Priority:** P1 · **Effort:** 4h · **Tests:** e2e `tests/e2e/screens.js`.

---

## EPIC D — Hall (Studio Rental) Synchronization (🟦/🟥)

### D-01 · mapping `hall_rental` / `location_rental`
- **Change:** Service Map → Items `STU-HALL-RENTAL-HOUR`, `STU-LOCATION-HOUR`; Resource = القاعة (Studio Service)؛ **لا** `resource_type=Hall`، **لا** `rental_model`. توثيق أن هذه ليست HAL.
- **Priority:** P0 · **Effort:** 1h (ضمن B-11) · **Tests:** حجز `hall_rental` يُستورد بمركز `استوديو X`.

### D-02 · حقول `deposit_due`, `price_pending`, `people`
- **Change:** ضمن B-02؛ `people` يُملأ عند A-08/F-04؛ تقرير يستثني `price_pending` من الإيراد.
- **Priority:** P1 · **Effort:** 2h

### D-03 · تقرير "Studio Bookings" (Script Report)
- **Existing:** `report/hall_bookings/` للقاعات فقط؛ لا تقرير استوديو (`known-issues.md:81`).
- **Change:** تقرير بالأعمدة: التاريخ، القاعة، العميل، النوع، الساعات، السعر، المطلوب، المدفوع، الحالة (ERP + XStudio)، الباقة/الساعات المخصومة، المصوّر، price_pending. فلاتر: فترة، قاعة، نوع، حالة.
- **Priority:** P1 · **Effort:** 5h · **Tests:** report test كما في `test_booking_pricing.py:757`.

### D-04 · قرار قاعات Imed (HAL) 🟥
- **Change:** لا كود. توثيق القرار Q-B6 في `docs/decisions/`.
- **Owner:** Business · **Priority:** P2

---

## EPIC E — Studio Packages & Session Consumption (🟦)

### E-01 · Upsert الباقة (إدراج + submit تلقائي)
- **Change:** `writers/packages.py`: Resource = `settings.packages_resource`; إدراج Draft ثم `submit()` بـ `flags.from_import`; تحديث الحقول المسموحة (`price`, `expires_on`, `xstudio_payment_status`, `package_name`, `hours_purchased` إذا تغيّر → تحذير) ; `Used Up/Active` تُحسب بعد الـ usage.
- **Priority:** P0 · **Effort:** 5h · **Tests:** الباقة المستوردة لا تُسحب منها بحجز يدوي (أو تُسحب؟ → قرار: **لا**، لأن الرصيد يُدار في XStudio).

### E-02 · استيراد `package_usage` كسطور Usage
- **Change:** `writers/usage.py append_usage(u)`: via `record()` بـ `external_id`; ترتيب بـ `created_at`; إن الحجز غير موجود بعد → Retry queue؛ إن الرصيد سيصبح سالباً (ترتيب خاطئ) → Retry.
- **Priority:** P0 · **Effort:** 4h · **Tests:** خصم ثم استرداد → الرصيد يعود؛ تكرار id مرفوض.

### E-03 · وحدة الريل
- **Change:** `unit=Reel` إذا `category='reels'` أو الاسم يطابق (`bookingService.js:78`)؛ التقارير تفصل الساعات عن الريلز؛ `Studio Hour Package` label ديناميكي.
- **Priority:** P1 · **Effort:** 2h

### E-04 · الانتهاء `expires_on`
- **Change:** حقل + فلتر في التقارير؛ لا تغيير حالة آلي (مطابق لسلوك XStudio).
- **Priority:** P2 · **Effort:** 1h

### E-05 · مطابقة رصيد الباقة
- **Change:** في `reconcile.py`: `hours_remaining` XStudio vs ERP → تقرير + (اختياري حسب Q-B10) سطر Usage تعويضي `reason="XStudio manual adjustment"`.
- **Priority:** P1 · **Effort:** 3h

### E-06 · الباقات المحذوفة في المصدر
- **Change:** في `run_full`: باقة في ERP غير موجودة في المصدر → `cancel_package(reason="deleted in XStudio")` إذا لا ساعات محجوزة، وإلا تنبيه. يعتمد على A-08/F-05 للحل الجذري.
- **Priority:** P1 · **Effort:** 2h

---

## EPIC F — Payments & Financial Integration (🟦/🟥)

### F-01 · استيراد الدفعات كـ mirror
- **Change:** `writers/payments.py mirror_payment(p)`: `XStudio Payment` upsert؛ `direction` من الإشارة/`method='refund'`؛ `mode_of_payment` من الmap (Needs Mapping لا يُفشِل)؛ تحديث `Booking.paid_amount` من Σ mirrors للحجز المستورد (بدل `payments_total` الذي يقرأ PE — `booking_accounts.py:178-185` يُفرَّع: Imported → mirrors).
- **Priority:** P0 · **Effort:** 5h · **Tests:** دفعة ثم استرداد → `paid_amount` 0؛ `payment_status` mapping.

### F-02 · Payment Method Map + UI
- **Change:** ضمن B-05/B-11؛ شاشة لإكمال Needs Mapping؛ تنبيه.
- **Priority:** P0 · **Effort:** 2h · **Business:** Q-B5.

### F-03 · ترحيل Payment Entry من mirrors (Phase 2) 🟥
- **Existing:** `booking_accounts.record_payment(booking, amount, mode, request_id, reference_no)` idempotent بـ `custom_booking_request` ويرفض Imported (`booking_accounts.py:250-251`).
- **Change:** `posting.post_payments()`: لكل mirror `Mirrored` + mapped: استدعاء نسخة داخلية `_record_payment(..., allow_imported=True)` بـ `request_id="xstudio:"+external_id`, `posting_date` من `posted_at`, remarks "XStudio payment {id} by {recorded_by_name}"; دفعة باقة → PE على party Customer بدون `custom_booking` مع `custom_hour_package` (حقل جديد) ; فشل `check_closed_days` → `Failed` + تنبيه؛ `Posted` + `payment_entry`. يُفعَّل بعلم `settings.post_payments` (افتراضي OFF).
- **Priority:** P1 (Phase 2) · **Effort:** 10h · **Tests:** لا PE مكرر عند تشغيل مرتين؛ GL على `خزينة X Studio`; يوم مُقفَل → Failed.
- **Business:** Q-B5, Q-B8.

### F-04 · Sales Invoice عند `completed` (Phase 2) 🟥
- **Existing:** `booking_accounts.complete/make_invoice` للـ Manual فقط (`booking_accounts.py:427-526`).
- **Change:** السماح للمستورد إذا `settings.post_invoices` و`price_pending=0`؛ البنود من Service Map (`xstudio_service_item`, qty=hours أو 1 للريلز، rate = `xstudio_price_total/hours`)؛ خصم `xstudio_discount_amount` كـ discount؛ ساعات الباقة → بند بسعر 0 أو استثناء حسب Q-B4؛ advances من PEs المرحَّلة.
- **Priority:** P2 · **Effort:** 10h · **Business:** Q-B2, Q-B4.

### F-05 · الاستردادات والإلغاء بعد الترحيل (Phase 2)
- **Change:** mirror سالب → PE Pay عكسي (نفس Mode)؛ إلغاء حجز له SI → Credit Note (`sales_cancellation.restrict_returns` قد يمنع → تنسيق) أو تنبيه يدوي.
- **Priority:** P2 · **Effort:** 6h

### F-06 · أيام مُقفَلة وتواريخ مستقبلية
- **Change:** عند `check_closed_days` فشل → `Failed` مع اقتراح؛ شاشة للمحاسب: "Post on today's date with note" أو reopen.
- **Priority:** P2 · **Effort:** 3h

### F-07 · مستحقات المصورين (Phase 3) 🟥
- **Change:** من `XStudio Week Closing`: JE Dr مصروف (حساب جديد `حصة المصورين` تحت المصروفات) / Cr `مستحقات للمصورين` (جديد) party Employee/Supplier؛ أو Expense doc. يعتمد Q-B7.
- **Priority:** P3 · **Effort:** 8h

### F-08 · سياسة إيراد الباقات 🟥
- **Change:** قرار Q-B4 → إما `studio_hour_package.make_invoice` آلي عند الاستيراد أو deferred.
- **Priority:** P2 · **Effort:** 4h بعد القرار

---

## EPIC G — Monitoring, Failures & Recovery (🟦)

### G-01 · حقول Import Log الجديدة (= B-10) و`ImportRun` API
- **Priority:** P0 · **Effort:** (ضمن B-10)

### G-02 · Sync State + health computation
- **Change:** `state.compute_health()` بعد كل تشغيل؛ عرض في Integration Status وOwner Dashboard (`owner_yesterday.booking_import()` يُستبدل ليقرأ State بدل `not_configured` — `owner_yesterday.py:256-264`).
- **Priority:** P0 · **Effort:** 3h · **Tests:** `test_owner_reports.py`.

### G-03 · Retry queue
- **Change:** `XStudio Sync Retry` (B-08) + معالجة في كل تشغيل؛ `Exhausted` بعد 10؛ زر Retry now.
- **Priority:** P0 · **Effort:** 4h · **Tests:** سجل فاشل يُعاد ويُحل بعد إضافة mapping.

### G-04 · Integration Status + صفحة XStudio Integration
- **Existing:** `report/integration_status/` (صف لكل source)؛ `reimport_period` للملفات.
- **Change:** صف `xstudio` بالأعمدة الجديدة؛ Page/Workspace "XStudio Integration": آخر 20 تشغيلاً، أخطاء مفتوحة، Needs Mapping، Retry queue، زر "Sync now" (whitelisted, Accounts Manager) و"Full sync tonight".
- **Priority:** P0 · **Effort:** 6h · **Tests:** `test_app_import.py:298` نمط.

### G-05 · التنبيهات
- **Change:** Notification/Email/System Notification لـ `settings.notify_users` عند: Down، Changed After Posting، Needs Mapping، Exhausted retries، فرق مطابقة مالي.
- **Priority:** P1 · **Effort:** 3h

### G-06 · تقرير المطابقة `XStudio Reconciliation` + `reconcile.run_daily`
- **Change:** الفحوص R1–R14 (§14 في التحليل)؛ تخزين النتائج في `XStudio Reconciliation Run` (jsonb-like Long Text + عدّادات)؛ **لا كتابة مالية**.
- **Priority:** P1 (R1–R6 في MVP) · **Effort:** 8h · **Tests:** فروق مصطنعة تُكتشف.

### G-07 · Runbook
- **Change:** `docs/integrations/xstudio/RUNBOOK.md`: تفعيل/تعطيل، تدوير المفتاح، إعادة مزامنة فترة، التعامل مع Exhausted، rollback.
- **Priority:** P1 · **Effort:** 3h

---

## EPIC H — QA & Deployment (🟨)

### H-01 · Mock XStudio server + fixtures
- **Change:** `APP/integrations/xstudio/tests/mock_server.py` (Flask/`http.server`) يخدم fixtures JSON مأخوذة من staging (`admin/export` مُنقَّى)؛ يُستعمل في `IntegrationTestCase`.
- **Priority:** P0 · **Effort:** 5h

### H-02 · Unit tests للـ mappers
- **Change:** كل حالات §8.5، 24:00، price_pending، reels، phone placeholder، hash stability.
- **Priority:** P0 · **Effort:** 4h

### H-03 · Idempotency tests
- **Change:** تشغيل incremental مرتين على نفس الصفحات → صفر inserted/updated؛ full بعد incremental → صفر تغييرات؛ تكرار دفعة → unique violation مُعالَج.
- **Priority:** P0 · **Effort:** 3h

### H-04 · Concurrency tests
- **Existing:** `test_booking.py:153` concurrent saves؛ `APP/setup/concurrency_check.py`.
- **Change:** حجز يدوي يُحفظ أثناء استيراد حجز متعارض → واحد فقط ينجح؛ تشغيلان للمزامنة → lock.
- **Priority:** P1 · **Effort:** 4h

### H-05 · Contract tests ضد staging
- **Change:** test يُشغَّل يدوياً/CI nightly: `health`, `config`, `integration/*` تطابق `openapi.yaml`.
- **Priority:** P1 · **Depends:** A-09, A-10 · **Effort:** 3h

### H-06 · UAT end-to-end
- **Change:** سكريبت UAT: في staging XStudio: إنشاء عميل، بيع باقة 10 ساعات مع دفعة، حجز ساعتين (خصم)، دفعة، نقل، إلغاء (استرداد)، إكمال؛ التحقق بعد ≤ 10 دقائق من كل أثر في ERP + تقرير المطابقة صفر فروق. Playwright في `tests/e2e/xstudio.js`.
- **Priority:** P0 · **Effort:** 6h (كتابة) + 3 أيام تنفيذ UAT

### H-07 · Permissions tests
- **Change:** Integration Runner لا يرى `قاعات Imed`؛ Branch Manager لا يعدّل XStudio Settings؛ Accounts Manager يرى mirrors.
- **Priority:** P0 · **Effort:** 2h

### H-08 · خطة الإطلاق (shadow → live)
- **Change:** (1) تشغيل على staging ERP ضد staging XStudio أسبوعاً؛ (2) إنتاج ERP ضد إنتاج XStudio بـ `post_payments=OFF, post_invoices=OFF` أسبوعين (shadow)؛ (3) مراجعة المطابقة يومياً؛ (4) go-live MVP = لا تغيير تقني، فقط اعتماد التقارير؛ (5) Phase 2 بعلم تدريجي.
- **Priority:** P0 · **Effort:** 2h كتابة · **Owner:** Both + Business

### H-09 · Rollback
- **Change:** `settings.enabled=0` يوقف كل شيء؛ السجلات المستوردة تبقى (لا حذف)؛ إجراء لإلغاء PEs مرحَّلة بالخطأ عبر فلتر `custom_booking_request like 'xstudio:%'` (Accounts Manager، يدوي، موثَّق).
- **Priority:** P0 · **Effort:** 2h

---

## الترتيب الموصى به (Critical path)

1. **أسبوع 1:** B-09, B-08, B-10 ‖ A-01, A-02, A-10 ‖ Q-B1, Q-B3, Q-B5 (business).
2. **أسبوع 2:** B-01..B-07, B-11, C-01, C-02, H-01, H-02 ‖ A-03, A-04, A-05.
3. **أسبوع 3:** C-03..C-07, E-01, E-02, F-01, F-02, D-01 ‖ A-06, A-07, A-08(F-05, F-02).
4. **أسبوع 4:** G-02..G-04, G-06 (R1–R6), C-08, H-03, H-04, H-07, H-09 → **staging shadow**.
5. **أسبوع 5–6:** C-05 (initial import على الإنتاج)، shadow run، H-06 UAT، G-05, G-07, D-03, E-03..E-06.
6. **Go-live MVP** → قرارات Phase 2 → F-03..F-08, A-09, A-11, webhook receiver.

## تصنيف العمل

| التصنيف | المهام |
|---|---|
| **ERP فقط (يمكن البدء الآن)** | B-01..B-11, C-01, C-02, C-08, D-01..D-03, E-01..E-06, F-01, F-02, G-01..G-07, H-01..H-04, H-07, H-09 |
| **XStudio فقط** | A-01..A-09, A-11, A-12 |
| **يحتاج وصول/نشر** | A-10 (staging), A-02 (مفتاح), C-05 (الإنتاج), H-05, H-06, H-08 |
| **قرار عمل قبل البدء** | C-04 (Q-B1), C-07 (Q-B3), F-02 (Q-B5), C-03 سياسة التحديث (Q-B9) |
| **قرار عمل قبل Phase 2** | F-03 (Q-B5, Q-B8), F-04 (Q-B2, Q-B4), F-07 (Q-B7), D-04 (Q-B6), E-05 (Q-B10) |
