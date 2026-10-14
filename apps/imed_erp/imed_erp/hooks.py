app_name = "imed_erp"
app_title = "ImedERP"
app_publisher = "toka mohamed"
app_description = "Custom app for Imed group"
app_email = "academyimed11@gmail.com"
app_license = "mit"

# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "imed_erp",
# 		"logo": "/assets/imed_erp/logo.png",
# 		"title": "ImedERP",
# 		"route": "/imed_erp",
# 		"has_permission": "imed_erp.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# IMED ERP theme: plain CSS (no build step), served from imed_erp/public at /assets/imed_erp.
app_include_css = [
	"/assets/imed_erp/css/imed_fonts.css",
	"/assets/imed_erp/css/imed_theme.css",
	"/assets/imed_erp/css/imed_assistant.css",
]
# Home screen: greeting band and quick actions; the AI assistant character + chat panel; a light/dark
# switch next to the notifications
# (all only add elements, see the files).
app_include_js = [
	# Reusable screen design standard (imed.screen.apply); loaded first so doctype scripts can use it.
	"/assets/imed_erp/js/imed_form_standard.js",
	"/assets/imed_erp/js/imed_home.js",
	"/assets/imed_erp/js/imed_assistant.js",
	"/assets/imed_erp/js/imed_theme_toggle.js",
]

# include js, css files in header of web template (the theme there only touches the login page)
web_include_css = ["/assets/imed_erp/css/imed_fonts.css", "/assets/imed_erp/css/imed_web.css"]
# web_include_js = "/assets/imed_erp/js/imed_erp.js"

# Branding: logo on the home screen and the login page, and the browser tab icon.
app_logo_url = "/assets/imed_erp/images/imed-mark.svg"
website_context = {
	"favicon": "/assets/imed_erp/images/imed-mark.svg",
	"splash_image": "/assets/imed_erp/images/imed-mark.svg",
}

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "imed_erp/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# Screen design standard applied to a standard ERPNext doctype (see docs/SCREEN_DESIGN_STANDARD.md).
doctype_js = {
	"Sales Invoice": "public/js/sales_invoice.js",
	"Material Request": "public/js/material_request.js",
	"Stock Entry": "public/js/stock_entry.js",
}
# The point of sale (LIB-01): one-click buttons for the library services, added to ERPNext's own page.
page_js = {"point-of-sale": "public/js/point_of_sale.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "imed_erp/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# automatically load and sync documents of this doctype from downstream apps
# importable_doctypes = [doctype_1]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "imed_erp.utils.jinja_methods",
# 	"filters": "imed_erp.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "imed_erp.install.before_install"
# after_install = "imed_erp.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "imed_erp.uninstall.before_uninstall"
# after_uninstall = "imed_erp.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "imed_erp.utils.before_app_install"
# after_app_install = "imed_erp.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "imed_erp.utils.before_app_uninstall"
# after_app_uninstall = "imed_erp.utils.after_app_uninstall"

# Build
# ------------------
# To hook into the build process

# after_build = "imed_erp.build.after_build"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "imed_erp.notifications.get_notification_config"

# Awesome Bar
# -----------
# Extra search results: list of dicts with label, description, route, index.
# route: ["List", "ToDo"], "/desk/docs/some/page", or "https://example.com"
# awesomebar_search = ["imed_erp.search.awesomebar_results"]

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# Document Events
# ---------------
# Hook on document methods and events

# doc_events = {
# 	"*": {
# 		"on_update": "method",
# 		"on_cancel": "method",
# 		"on_trash": "method"
# 	}
# }

# Every event of a doctype in one entry: two entries for the same doctype would replace each other.
# on_trash: a submitted or cancelled financial document is never deleted (imederp/no_delete.py).
# validate and before_cancel on the app's documents: none is saved or cancelled in a closed month or academic
# period (imederp/period_lock.py).
# on_submit on stock documents, and Item validate: reorder levels per item and warehouse (LIB-04).
# Stock Reconciliation validate: an opening count is ERPNext's Opening Stock; the difference is the
# branch's (imederp/stock_count.py).
doc_events = {
	"Journal Entry": {
		"validate": [
			"imed_erp.imederp.doctype.inter_business_transfer.inter_business_transfer.block_manual_current_account",
			"imed_erp.imederp.treasuries.check_entry_treasuries",
		],
		"before_cancel": [
			"imed_erp.imederp.doctype.expense.expense.block_cancel_of_expense_entry",
			"imed_erp.imederp.doctype.inter_business_transfer.inter_business_transfer.block_cancel_of_transfer_entry",
		],
		"on_trash": "imed_erp.imederp.no_delete.block_delete_of_posted",
	},
	"Payment Entry": {
		"validate": [
			"imed_erp.imederp.doctype.inter_business_transfer.inter_business_transfer.block_current_account_in_payment",
			"imed_erp.imederp.treasuries.block_spending_without_approval",
			"imed_erp.imederp.treasuries.check_entry_treasuries",
		],
		"before_cancel": "imed_erp.imederp.damaged_stock.block_cancel_of_posted_entry",
		"on_trash": "imed_erp.imederp.no_delete.block_delete_of_posted",
	},
	"Sales Invoice": {
		"validate": [
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
		],
		"on_trash": "imed_erp.imederp.no_delete.block_delete_of_posted",
		"on_submit": [
			"imed_erp.imederp.stock_reorder.alert_on_reorder_level",
			# Printing and copying sold take their paper out of the library's store (imederp/paper_use.py).
			"imed_erp.imederp.paper_use.issue_paper_used",
			"imed_erp.imederp.edition_sales.update_sold",
			# The doctor's amount on each copy sold goes to his ledger (DOC-07; imederp/doctor_accrual.py).
			"imed_erp.imederp.doctor_accrual.accrue",
		],
		"on_cancel": [
			"imed_erp.imederp.paper_use.cancel_paper_used",
			"imed_erp.imederp.edition_sales.update_sold",
			"imed_erp.imederp.doctor_accrual.cancel_accruals",
		],
	},
	"POS Invoice": {
		"validate": [
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
		],
		"on_submit": "imed_erp.imederp.stock_reorder.alert_on_reorder_level",
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
		],
		"on_submit": "imed_erp.imederp.stock_reorder.alert_on_reorder_level",
		"on_trash": "imed_erp.imederp.no_delete.block_delete_of_posted",
	},
	"Delivery Note": {
		"validate": "imed_erp.imederp.damaged_stock.guard_damaged_store",
		"on_submit": "imed_erp.imederp.stock_reorder.alert_on_reorder_level",
		"on_trash": "imed_erp.imederp.no_delete.block_delete_of_posted",
	},
	"Purchase Receipt": {
		"on_submit": "imed_erp.imederp.stock_reorder.alert_on_reorder_level",
		"on_trash": "imed_erp.imederp.no_delete.block_delete_of_posted",
	},
	"Stock Reconciliation": {
		"validate": [
			"imed_erp.imederp.stock_count.check_count_type",
			"imed_erp.imederp.stock_count.set_branch_cost_center",
		],
		"before_cancel": "imed_erp.imederp.doctype.stock_count.stock_count.block_cancel_of_count_reconciliation",
		"on_submit": "imed_erp.imederp.stock_reorder.alert_on_reorder_level",
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
		"before_cancel": "imed_erp.imederp.period_lock.validate_closed_period",
	},
	"App Subscription": {
		"on_trash": "imed_erp.imederp.no_delete.block_delete_of_posted",
		"validate": "imed_erp.imederp.period_lock.validate_closed_period",
		"before_cancel": "imed_erp.imederp.period_lock.validate_closed_period",
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
	},
}
# Month-end closing (setup/close_period.py) also locks the app's own documents (imederp/period_lock.py).
period_closing_doctypes = [
	"Expense",
	"Inter Business Transfer",
	"Doctor Ledger Entry",
	"App Subscription",
	"Printer Reading",
	"Stock Count",
	"Damaged Stock Entry",
	"Damaged Stock Sale",
]

# The custom fields the app's code relies on: made when the app is installed (install-app does not run
# after_migrate) and kept in step with the code on every migrate.
after_install = [
	"imed_erp.imederp.material_issue.make_custom_fields",
	"imed_erp.imederp.damaged_stock.make_custom_fields",
	"imed_erp.imederp.customers.make_custom_fields",
	"imed_erp.imederp.sales_cancellation.make_custom_fields",
	"imed_erp.imederp.edition_sales.make_custom_fields",
]
after_migrate = [
	"imed_erp.imederp.material_issue.make_custom_fields",
	"imed_erp.imederp.damaged_stock.make_custom_fields",
	"imed_erp.imederp.customers.make_custom_fields",
	"imed_erp.imederp.sales_cancellation.make_custom_fields",
	"imed_erp.imederp.edition_sales.make_custom_fields",
]

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"imed_erp.tasks.all"
# 	],
# 	"daily": [
# 		"imed_erp.tasks.daily"
# 	],
# 	"hourly": [
# 		"imed_erp.tasks.hourly"
# 	],
# 	"weekly": [
# 		"imed_erp.tasks.weekly"
# 	],
# 	"monthly": [
# 		"imed_erp.tasks.monthly"
# 	],
# }

scheduler_events = {
	"daily": [
		"imed_erp.imederp.doctype.recurring_expense.recurring_expense.run_daily",
	],
}

# Testing
# -------

# before_tests = "imed_erp.install.before_tests"

# Extend DocType Class
# ------------------------------
#
# Specify custom mixins to extend the standard doctype controller.
# extend_doctype_class = {
# 	"Task": "imed_erp.custom.task.CustomTaskMixin"
# }

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "imed_erp.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "imed_erp.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["imed_erp.utils.before_request"]
# after_request = ["imed_erp.utils.after_request"]

# Job Events
# ----------
# before_job = ["imed_erp.utils.before_job"]
# after_job = ["imed_erp.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"imed_erp.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# Translation
# ------------
# List of apps whose translatable strings should be excluded from this app's translations.
# ignore_translatable_strings_from = []

