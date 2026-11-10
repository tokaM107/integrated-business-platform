import os

app_name = "imed_erp"
app_title = "ImedERP"
app_publisher = "toka mohamed"
app_description = "Custom app for Imed group"
app_email = "academyimed11@gmail.com"
app_license = "mit"

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# IMED ERP theme: plain CSS (no build step), served from imed_erp/public at /assets/imed_erp.


def asset(path):
	"""/assets/imed_erp/<path>?v=<when the file last changed>. These files are not built (no hash in their name)
	and are sent with no caching rule, so a browser kept its old copy after a change (21 Oct 2026: the owner saw
	the old home screen). A new address after each change makes every browser fetch it again."""
	try:
		version = int(os.path.getmtime(os.path.join(os.path.dirname(__file__), "public", path)))
	except OSError:
		version = 0
	return f"/assets/imed_erp/{path}?v={version}"


app_include_css = [
	asset("css/imed_fonts.css"),
	asset("css/imed_theme.css"),
	asset("css/imed_assistant.css"),
]
# Home screen: greeting band and quick actions; the AI assistant character + chat panel; a light/dark
# switch next to the notifications
# (all only add elements, see the files).
app_include_js = [
	# Reusable screen design standard (imed.screen.apply); loaded first so doctype scripts can use it.
	asset("js/imed_form_standard.js"),
	asset("js/imed_home.js"),
	asset("js/imed_assistant.js"),
	# The Owner Dashboard's welcome band, card icons and colours.
	asset("js/imed_owner_dashboard.js"),
	asset("js/imed_theme_toggle.js"),
	# "Log out" at the bottom of the sidebar.
	asset("js/imed_sidebar.js"),
	# Fixes to Frappe's desk seen in the browser (a broken icon in the sidebar menu).
	asset("js/imed_desk_fixes.js"),
	# Lists and reports: the filters in a side panel, a few of them; a report's PDF and Print (owner, 9 Nov 2026).
	asset("js/imed_lists.js"),
]

# include js, css files in header of web template (the theme there only touches the login page)
# Versioned like the desk's (asset()): the sign-in page's look changed on 2 Nov 2026 and browsers kept the old copy.
web_include_css = [asset("css/imed_fonts.css"), asset("css/imed_web.css")]
# web_include_js = "/assets/imed_erp/js/imed_erp.js"

# Branding: logo on the home screen and the login page, and the browser tab icon.
app_logo_url = "/assets/imed_erp/images/imed-mark.svg"
website_context = {
	"favicon": "/assets/imed_erp/images/imed-mark.svg",
	"splash_image": "/assets/imed_erp/images/imed-mark.svg",
}

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "imed_erp/public/scss/website"

# include js in doctype views
# Screen design standard applied to a standard ERPNext doctype (see docs/standards/screen-design-standard.md).
doctype_js = {
	"Sales Invoice": "public/js/sales_invoice.js",
	"Material Request": "public/js/material_request.js",
	"Stock Entry": "public/js/stock_entry.js",
	# DOC-29: a doctor's agreements and their balances on his file.
	"Customer": "public/js/customer.js",
	# LIB-07: the purchase invoice screen, only what buying paper and materials needs.
	"Purchase Invoice": "public/js/purchase_invoice.js",
}
# The point of sale (LIB-01): one-click buttons for the library services, added to ERPNext's own page.
page_js = {"point-of-sale": "public/js/point_of_sale.js"}

# Document Events
# ---------------
# Hook on document methods and events

# Every event of a doctype in one entry: two entries for the same doctype would replace each other.
# on_trash: a submitted or cancelled financial document is never deleted (imederp/no_delete.py).
# validate and before_cancel on the app's documents: none is saved or cancelled in a closed month or academic
# period (imederp/period_lock.py).
# on_submit on stock documents, and Item validate: reorder levels per item and warehouse (LIB-04).
# Stock Reconciliation validate: an opening count is ERPNext's Opening Stock; the difference is the
# branch's (imederp/stock_count.py).
# The AI assistant's integrations (assistant/core/interfaces.py, BusinessIntegration): dotted paths to callables
# `f(context) -> list[BusinessIntegration]`. This app registers its own; another app adds its own in its hooks.py.
# The assistant's core never changes for a new business.
assistant_businesses = ["imed_erp.assistant.businesses.imed.integrations"]

# Saved assistant chats are their user's alone, in the desk and the REST API too, not only in the chat window.
has_permission = {
	"Assistant Chat": "imed_erp.imederp.doctype.assistant_chat.assistant_chat.has_permission",
	"Assistant Message": "imed_erp.imederp.doctype.assistant_message.assistant_message.has_permission",
}
permission_query_conditions = {
	"Assistant Chat": "imed_erp.imederp.doctype.assistant_chat.assistant_chat.query_conditions",
	"Assistant Message": "imed_erp.imederp.doctype.assistant_message.assistant_message.query_conditions",
	# A branch manager lists their own branch's journal entries only (imederp/branch_lists.py).
	"Journal Entry": "imed_erp.imederp.branch_lists.journal_entry_conditions",
	"Stock Entry": "imed_erp.imederp.branch_lists.stock_entry_conditions",
}

doc_events = {
	# No completed transaction dated after today (QA-24; imederp/dates.py lists the doctypes).
	"*": {
		"validate": "imed_erp.imederp.dates.refuse_future_date",
		# A cash box never goes below zero, whatever pays out of it (imederp/cash_balance.py). After the document's
		# own on_submit and on_cancel, which post its ledger lines.
		"on_submit": [
			"imed_erp.imederp.cash_balance.check_on_submit",
			"imed_erp.imederp.doctype.treasury_close.treasury_close.check_closed_days",
		],
		"before_cancel": "imed_erp.imederp.cash_balance.remember_before_cancel",
		"on_cancel": [
			"imed_erp.imederp.cash_balance.check_on_cancel",
			"imed_erp.imederp.doctype.treasury_close.treasury_close.check_closed_days",
		],
	},
	"Journal Entry": {
		"validate": [
			"imed_erp.imederp.doctype.inter_business_transfer.inter_business_transfer.block_manual_current_account",
			"imed_erp.imederp.treasuries.check_entry_treasuries",
		],
		# A booking's figures follow its revenue-share entry (imederp/booking_accounts.py).
		"on_submit": "imed_erp.imederp.booking_accounts.on_posted_change",
		"on_cancel": "imed_erp.imederp.booking_accounts.on_posted_change",
		"before_cancel": [
			"imed_erp.imederp.doctype.expense.expense.block_cancel_of_expense_entry",
			"imed_erp.imederp.doctype.inter_business_transfer.inter_business_transfer.block_cancel_of_transfer_entry",
			"imed_erp.imederp.doctype.app_payment.app_payment.block_cancel_of_payment_entry",
			"imed_erp.imederp.doctype.cash_handover.cash_handover.block_cancel_of_handover_entry",
			# The doctor's amount posted by a sale goes only with the sale (imederp/doctor_accrual.py).
			"imed_erp.imederp.doctor_accrual.block_cancel_of_accrual",
		],
		"on_trash": "imed_erp.imederp.no_delete.block_delete_of_posted",
	},
	"Payment Entry": {
		"validate": [
			"imed_erp.imederp.doctype.inter_business_transfer.inter_business_transfer.block_current_account_in_payment",
			"imed_erp.imederp.treasuries.block_spending_without_approval",
			"imed_erp.imederp.treasuries.check_entry_treasuries",
			"imed_erp.imederp.booking_accounts.guard_booking_link",
		],
		"before_cancel": "imed_erp.imederp.damaged_stock.block_cancel_of_posted_entry",
		"on_trash": "imed_erp.imederp.no_delete.block_delete_of_posted",
		# A booking's Amount Paid follows its deposits and payments (imederp/booking_accounts.py).
		"on_submit": "imed_erp.imederp.booking_accounts.on_posted_change",
		"on_cancel": "imed_erp.imederp.booking_accounts.on_posted_change",
	},
	"Sales Invoice": {
		"validate": [
			"imed_erp.imederp.sales_cancellation.restrict_returns",
			"imed_erp.imederp.library_revenue.set_library_income_account",
			"imed_erp.imederp.treasuries.check_entry_treasuries",
			"imed_erp.imederp.services.clear_service_warehouses",
			"imed_erp.imederp.damaged_stock.guard_damaged_store",
			# Each copy of a book or memo sold names its edition (DOC-14..17; imederp/edition_sales.py).
			"imed_erp.imederp.edition_sales.set_editions",
		],
		"before_cancel": [
			"imed_erp.imederp.damaged_stock.block_cancel_of_posted_entry",
			# A sale is cancelled only with its reason (ACC-06; imederp/sales_cancellation.py).
			"imed_erp.imederp.sales_cancellation.require_cancel_reason",
			"imed_erp.imederp.stock_reorder.remember_stock_before_cancel",
		],
		"on_trash": "imed_erp.imederp.no_delete.block_delete_of_posted",
		"on_submit": [
			"imed_erp.imederp.stock_reorder.alert_on_reorder_level",
			# Printing and copying sold take their paper out of the library's store (imederp/paper_use.py).
			"imed_erp.imederp.paper_use.issue_paper_used",
			# The day's counters of the library take in what was sold (PRN-02).
			"imed_erp.imederp.paper_use.refresh_counters",
			"imed_erp.imederp.edition_sales.update_sold",
			# The doctor's amount on each copy sold goes to his ledger (DOC-07; imederp/doctor_accrual.py).
			"imed_erp.imederp.doctor_accrual.accrue",
			# A booking's invoice (imederp/booking_accounts.py).
			"imed_erp.imederp.booking_accounts.on_posted_change",
		],
		"on_cancel": [
			"imed_erp.imederp.stock_reorder.alert_on_reorder_level",
			"imed_erp.imederp.paper_use.cancel_paper_used",
			"imed_erp.imederp.paper_use.refresh_counters",
			"imed_erp.imederp.edition_sales.update_sold",
			"imed_erp.imederp.doctor_accrual.cancel_accruals",
			"imed_erp.imederp.booking_accounts.on_posted_change",
		],
	},
	"POS Invoice": {
		"validate": [
			"imed_erp.imederp.sales_cancellation.restrict_returns",
			"imed_erp.imederp.library_revenue.set_library_income_account",
			"imed_erp.imederp.treasuries.check_entry_treasuries",
			"imed_erp.imederp.services.clear_service_warehouses",
			"imed_erp.imederp.damaged_stock.guard_damaged_store",
		],
		"on_trash": "imed_erp.imederp.no_delete.block_delete_of_posted",
	},
	"Purchase Invoice": {
		"validate": [
			"imed_erp.imederp.treasuries.block_spending_without_approval",
			"imed_erp.imederp.treasuries.check_entry_treasuries",
			"imed_erp.imederp.damaged_stock.guard_damaged_store",
		],
		"on_submit": "imed_erp.imederp.stock_reorder.alert_on_reorder_level",
		"before_cancel": "imed_erp.imederp.stock_reorder.remember_stock_before_cancel",
		"on_cancel": "imed_erp.imederp.stock_reorder.alert_on_reorder_level",
		"on_trash": "imed_erp.imederp.no_delete.block_delete_of_posted",
	},
	"Stock Entry": {
		# validate and before_submit: the issue of a branch request (imederp/material_issue.py); the damaged
		# store moves only through a damage record or a sale by weight (imederp/damaged_stock.py).
		"validate": [
			"imed_erp.imederp.material_issue.validate_stock_entry",
			"imed_erp.imederp.damaged_stock.guard_damaged_store",
		],
		"before_submit": "imed_erp.imederp.material_issue.before_submit_stock_entry",
		# Entries posted by a printing sale's paper, a damage record or a sale by weight are cancelled only
		# through it (imederp/paper_use.py, imederp/damaged_stock.py).
		"before_cancel": [
			"imed_erp.imederp.paper_use.block_cancel_of_paper_issue",
			"imed_erp.imederp.damaged_stock.block_cancel_of_posted_entry",
			"imed_erp.imederp.stock_reorder.remember_stock_before_cancel",
		],
		"on_submit": "imed_erp.imederp.stock_reorder.alert_on_reorder_level",
		"on_cancel": "imed_erp.imederp.stock_reorder.alert_on_reorder_level",
		"on_trash": "imed_erp.imederp.no_delete.block_delete_of_posted",
	},
	"Delivery Note": {
		"validate": "imed_erp.imederp.damaged_stock.guard_damaged_store",
		"on_submit": "imed_erp.imederp.stock_reorder.alert_on_reorder_level",
		"before_cancel": "imed_erp.imederp.stock_reorder.remember_stock_before_cancel",
		"on_cancel": "imed_erp.imederp.stock_reorder.alert_on_reorder_level",
		"on_trash": "imed_erp.imederp.no_delete.block_delete_of_posted",
	},
	"Purchase Receipt": {
		"validate": "imed_erp.imederp.damaged_stock.guard_damaged_store",
		"on_submit": "imed_erp.imederp.stock_reorder.alert_on_reorder_level",
		"before_cancel": "imed_erp.imederp.stock_reorder.remember_stock_before_cancel",
		"on_cancel": "imed_erp.imederp.stock_reorder.alert_on_reorder_level",
		"on_trash": "imed_erp.imederp.no_delete.block_delete_of_posted",
	},
	"Stock Reconciliation": {
		"validate": [
			"imed_erp.imederp.stock_count.check_count_type",
			"imed_erp.imederp.stock_count.set_branch_cost_center",
		],
		"before_cancel": [
			"imed_erp.imederp.doctype.stock_count.stock_count.block_cancel_of_count_reconciliation",
			"imed_erp.imederp.stock_reorder.remember_stock_before_cancel",
		],
		"on_submit": "imed_erp.imederp.stock_reorder.alert_on_reorder_level",
		"on_cancel": "imed_erp.imederp.stock_reorder.alert_on_reorder_level",
		"on_trash": "imed_erp.imederp.no_delete.block_delete_of_posted",
	},
	"Cost Center Allocation": {
		"on_trash": "imed_erp.imederp.no_delete.block_delete_of_posted",
	},
	"Expense": {
		"on_trash": "imed_erp.imederp.no_delete.block_delete_of_posted",
		"validate": "imed_erp.imederp.period_lock.validate_closed_period",
		"before_cancel": "imed_erp.imederp.period_lock.validate_closed_period",
	},
	"Inter Business Transfer": {
		"on_trash": "imed_erp.imederp.no_delete.block_delete_of_posted",
		"validate": "imed_erp.imederp.period_lock.validate_closed_period",
		"before_cancel": "imed_erp.imederp.period_lock.validate_closed_period",
	},
	"Doctor Agreement": {
		"on_trash": "imed_erp.imederp.no_delete.block_delete_of_posted",
	},
	"Doctor Ledger Entry": {
		"on_trash": "imed_erp.imederp.no_delete.block_delete_of_posted",
		"validate": "imed_erp.imederp.period_lock.validate_closed_period",
		"before_cancel": [
			"imed_erp.imederp.period_lock.validate_closed_period",
			"imed_erp.imederp.doctor_accrual.block_cancel_of_accrual",
		],
	},
	"App Subscription": {
		"on_trash": "imed_erp.imederp.no_delete.block_delete_of_posted",
		"validate": "imed_erp.imederp.period_lock.validate_closed_period",
		"before_cancel": "imed_erp.imederp.period_lock.validate_closed_period",
		# APP-03: the course's student count, tier and fee are counted again (also when a student withdraws).
		"on_submit": "imed_erp.imederp.doctype.app_course.app_course.on_subscription_change",
		"on_cancel": "imed_erp.imederp.doctype.app_course.app_course.on_subscription_change",
		"on_update_after_submit": "imed_erp.imederp.doctype.app_course.app_course.on_subscription_change",
	},
	"Book Edition": {
		"on_trash": "imed_erp.imederp.no_delete.block_delete_of_posted",
	},
	"Stock Count": {
		"on_trash": "imed_erp.imederp.no_delete.block_delete_of_posted",
		"validate": "imed_erp.imederp.period_lock.validate_closed_period",
		"before_cancel": "imed_erp.imederp.period_lock.validate_closed_period",
	},
	"Printer Reading": {
		"on_trash": "imed_erp.imederp.no_delete.block_delete_of_posted",
		"validate": "imed_erp.imederp.period_lock.validate_closed_period",
		"before_cancel": "imed_erp.imederp.period_lock.validate_closed_period",
	},
	"Daily Counter Reading": {
		"on_trash": "imed_erp.imederp.no_delete.block_delete_of_posted",
		"validate": "imed_erp.imederp.period_lock.validate_closed_period",
		"before_cancel": "imed_erp.imederp.period_lock.validate_closed_period",
	},
	"Allocation Rule": {
		"on_trash": "imed_erp.imederp.no_delete.block_delete_of_posted",
	},
	# Damaged stock and its sale by weight (LIB-09, PRN-07, DOC-19; imederp/damaged_stock.py).
	"Damaged Stock Entry": {
		"on_trash": "imed_erp.imederp.no_delete.block_delete_of_posted",
		"validate": "imed_erp.imederp.period_lock.validate_closed_period",
		"before_cancel": "imed_erp.imederp.period_lock.validate_closed_period",
	},
	"Damaged Stock Sale": {
		"on_trash": "imed_erp.imederp.no_delete.block_delete_of_posted",
		"validate": "imed_erp.imederp.period_lock.validate_closed_period",
		"before_cancel": "imed_erp.imederp.period_lock.validate_closed_period",
	},
	"Item": {
		"validate": "imed_erp.imederp.stock_reorder.validate_reorder_levels",
	},
	# One customer per phone number (CRM-01, CRM-04; imederp/customers.py).
	"Customer": {
		"validate": "imed_erp.imederp.customers.set_phone_key",
	},
	"Contact": {
		"validate": "imed_erp.imederp.customers.check_contact_phone",
		"on_update": "imed_erp.imederp.customers.sync_contact_phone",
	},
	# Branch requests from the main warehouse: Raghad's approval, then the issue (imederp/material_issue.py).
	"Material Request": {
		"onload": "imed_erp.imederp.material_issue.material_request_onload",
		"validate": "imed_erp.imederp.material_issue.validate_material_request",
		"before_submit": "imed_erp.imederp.material_issue.before_submit_material_request",
		"on_trash": "imed_erp.imederp.no_delete.block_delete_of_posted",
	},
	# SEC-12: kept once they carry money, postings, students or fees (imederp/no_delete.py).
	"Platform Fee Schedule": {
		"on_trash": "imed_erp.imederp.no_delete.block_delete_of_posted",
	},
	"Booking": {
		"on_trash": "imed_erp.imederp.no_delete.block_delete_of_kept",
	},
	"App Course": {
		"on_trash": "imed_erp.imederp.no_delete.block_delete_of_kept",
	},
	"Treasury Close": {
		"on_trash": "imed_erp.imederp.no_delete.block_delete_of_posted",
	},
	"Weekly Cash Reconciliation": {
		"on_trash": "imed_erp.imederp.no_delete.block_delete_of_posted",
	},
	# What students pay BA Plus (App Payment), the weekly cash hand-over (Cash Handover, ACC-09) and the studio's
	# prepaid hours (Studio Hour Package), 22 Oct 2026.
	"App Payment": {
		"on_trash": "imed_erp.imederp.no_delete.block_delete_of_posted",
		"validate": "imed_erp.imederp.period_lock.validate_closed_period",
		"before_cancel": "imed_erp.imederp.period_lock.validate_closed_period",
	},
	"Cash Handover": {
		"on_trash": "imed_erp.imederp.no_delete.block_delete_of_posted",
		"validate": "imed_erp.imederp.period_lock.validate_closed_period",
		"before_cancel": "imed_erp.imederp.period_lock.validate_closed_period",
	},
	"Studio Hour Package": {
		"on_trash": "imed_erp.imederp.no_delete.block_delete_of_posted",
		"validate": "imed_erp.imederp.period_lock.validate_closed_period",
		"before_cancel": "imed_erp.imederp.period_lock.validate_closed_period",
	},
	# A confirmed hand-over's signed receipt is kept (cash_handover.py).
	"File": {
		"on_trash": "imed_erp.imederp.doctype.cash_handover.cash_handover.keep_signed_receipt",
	},
	# CORE-07: a user is disabled, never deleted (imederp/users.py).
	"User": {
		"on_trash": "imed_erp.imederp.users.block_user_delete",
	},
}
# Month-end closing (setup/close_period.py) also locks the app's own documents (imederp/period_lock.py).
period_closing_doctypes = [
	"Expense",
	"Inter Business Transfer",
	"Doctor Ledger Entry",
	"App Subscription",
	"Printer Reading",
	"Daily Counter Reading",
	"Stock Count",
	"Damaged Stock Entry",
	"Damaged Stock Sale",
	"App Payment",
	"Cash Handover",
	"Studio Hour Package",
]

# The custom fields the app's code relies on: made when the app is installed (install-app does not run
# after_migrate) and kept in step with the code on every migrate.
# (A name starting with "_" is not a hook: Frappe skips it.)
_custom_fields = [
	"imed_erp.imederp.material_issue.make_custom_fields",
	"imed_erp.imederp.sparkle.fields.make_custom_fields",
	"imed_erp.imederp.booking_accounts.make_custom_fields",
	"imed_erp.imederp.damaged_stock.make_custom_fields",
	"imed_erp.imederp.customers.make_custom_fields",
	"imed_erp.imederp.sales_cancellation.make_custom_fields",
	"imed_erp.imederp.edition_sales.make_custom_fields",
	"imed_erp.imederp.xstudio.fields.make_custom_fields",
]
after_install = [*_custom_fields]
after_migrate = [
	*_custom_fields,
	# The home screen's tiles: what the group uses (imederp/home_screen.py).
	"imed_erp.imederp.home_screen.tidy_home",
	# The library documents' index by library and date (Frappe adds it only when the doctype itself changes).
	"imed_erp.imederp.doctype.library_sales_document.library_sales_document.on_doctype_update",
]

# The booking screens' statuses and colours, from imederp/booking_rules.py.
boot_session = "imed_erp.imederp.booking_rules.boot_session"

# Scheduled Tasks
# ---------------

scheduler_events = {
	"cron": {
		# XStudio's bookings, customers and prepaid packages, read from its API (imederp/xstudio/sync.py); the
		# settings say whether it is on and how many minutes between runs.
		"*/10 * * * *": [
			"imed_erp.imederp.xstudio.sync.run_scheduled",
			# The halls' bookings and payments, read from Sparkle (imederp/sparkle/sync.py, owner, 5 Nov 2026).
			"imed_erp.imederp.sparkle.sync.run_scheduled",
		],
	},
	"daily": [
		"imed_erp.imederp.doctype.recurring_expense.recurring_expense.run_daily",
		# The doctor's amount on any sale the hooks missed, e.g. imported ones (imederp/doctor_accrual.py).
		"imed_erp.imederp.doctor_accrual.run_daily",
	],
}
