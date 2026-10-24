# BA Plus's daily file (INT-05, APP-13): its courses and their students' subscriptions, by their ids in BA Plus,
# into App Course and submitted App Subscription. The file's columns are in docs/IMPORT_DATA_STANDARD.md, part 3.
#
# Run (the file on the server, as the integration user or an accountant; commits at the end):
#   bench --site frontend execute imed_erp.imederp.app_import.import_file --kwargs '{"path": "/path/app.csv"}'
#
# Every row is one subscription:
#   its id already imported, the same     skipped
#   its id already imported, now changed  listed as Changed in Source, NOT overwritten (INT-01): the accountant
#                                         decides, e.g. cancels it here and lets the next import bring it again
#   new                                   the doctor's app agreement found by his BA Plus id (Doctor Agreement
#                                         ba_plus_doctor_id), the course by its BA Plus id (made the first time,
#                                         in the term the subscription's date falls in), the student by phone (made
#                                         the first time), then the subscription is submitted: the course is
#                                         counted again and the change posted to the doctor's account, as for one
#                                         entered by hand (app_course.recalculate_course, platform_fee_posting.py)
#   anything wrong                        the row fails with its reason; nothing of it is kept; the others go on
# Nothing is checked less because it comes from a file: the subscription, the course and the student go through
# their own validation, and the user running the import needs the rights to make them.
#
# The platform fee is never read from the file: the ERP works it out (APP-02/03). The run is written to an
# Integration Import Log (integration_import_log.py), the rows to look at with their reasons.

import csv
import io

import frappe
from frappe import _
from frappe.utils import cstr, getdate

from imed_erp.imederp.customers import customer_with_phone, normalize_phone
from imed_erp.imederp.doctype.integration_import_log.integration_import_log import ImportRun

SOURCE = "ba_plus"
COLUMNS = ("subscription_id", "subscription_date", "course_id", "course_name", "doctor_id", "student_phone", "student_name")
STUDENT_GROUP = "طالب"


class ImportInterrupted(Exception):
	"""The database dropped the whole transaction (a deadlock): nothing of the run is left to keep."""


def import_file(path):
	with open(path, "rb") as f:
		content = f.read()
	log = import_content(content, file_name=path.rsplit("/", 1)[-1])
	frappe.db.commit()
	return log.name


def import_content(content, file_name=None):
	text = content.decode("utf-8-sig") if isinstance(content, bytes) else cstr(content)
	reader = csv.DictReader(io.StringIO(text))
	missing = [column for column in COLUMNS if column not in (reader.fieldnames or [])]
	if missing:
		frappe.throw(_("The file has no column {0}.").format(", ".join(missing)), title=_("Wrong File"))
	return import_rows(list(reader), file_name=file_name, content=content)


def import_rows(rows, file_name=None, content=None):
	"""Import the rows (dicts with COLUMNS) and return the run's Integration Import Log. Does not commit: the
	caller does (import_file), so a test can roll it back."""
	for doctype in ("App Subscription", "App Course"):
		if not frappe.has_permission(doctype, "create"):
			frappe.throw(_("You may not make an {0}, so you may not import them.").format(_(doctype)), frappe.PermissionError)
	run = ImportRun(SOURCE, file_name, content)
	made = {"App Course": [], "App Subscription": []}
	noted = set()
	try:
		# The header is the file's line 1.
		for row_no, row in enumerate(rows, start=2):
			row = frappe._dict({k: cstr(v).strip() for k, v in row.items() if k})
			run.read()
			frappe.db.savepoint("app_import_row")
			try:
				outcome = import_row(row)
			except Exception as e:
				try:
					frappe.db.rollback(save_point="app_import_row")
				except Exception as lost:
					raise ImportInterrupted(
						_("The import stopped at line {0}: the database dropped the run ({1}). Nothing was kept; run it again.").format(row_no, lost)
					) from lost
				frappe.clear_messages()
				run.failed(row_no, row.subscription_id, cstr(getattr(e, "message", None) or e))
				continue
			# Counted only once the row is kept: what a failed row made was rolled back with it.
			if outcome["result"] == "skipped":
				run.skipped()
			elif outcome["result"] == "changed":
				run.changed(row_no, row.subscription_id, outcome["reason"])
			else:
				run.inserted()
			for doctype, name in outcome.get("made", []):
				made.setdefault(doctype, []).append(name)
			run.created(outcome.get("created", 0))
			# A course renamed in BA Plus is listed once a run, however many of its students come.
			for external_id, reason in outcome.get("notes", []):
				if external_id not in noted:
					noted.add(external_id)
					run.changed(row_no, external_id, reason)
	except ImportInterrupted as e:
		frappe.db.rollback()
		return run.abort(e)
	log = run.finish()
	# Each imported record names the run that brought it.
	for doctype, names in made.items():
		for name in names:
			frappe.db.set_value(doctype, name, "import_log", log.name, update_modified=False)
	return log


def import_row(row):
	"""One row. Returns {"result": "inserted" | "skipped" | "changed", "reason", "made": [(doctype, name)],
	"created": records made on the way, "notes": [(external_id, change listed)]}; raises with the reason when the
	row cannot be imported."""
	if row.get("source_system") and row.source_system != SOURCE:
		frappe.throw(_("The row is from {0}, not BA Plus.").format(row.source_system))
	for column in COLUMNS:
		if not row.get(column):
			frappe.throw(_("{0} is empty.").format(column))
	date = getdate(row.subscription_date)
	student_key = normalize_phone(row.student_phone)

	existing = frappe.db.get_value(
		"App Subscription", {"import_key": key(row.subscription_id)}, ["name", "course", "student", "subscription_date", "docstatus"], as_dict=True
	)
	if existing:
		changes = subscription_changes(existing, row, date, student_key)
		note = course_renamed(row)
		notes = [(row.course_id, note)] if note else []
		if changes:
			reason = _("{0} differs from {1}: {2}.").format(row.subscription_id, existing.name, "; ".join(changes))
			return {"result": "changed", "reason": reason, "notes": notes}
		return {"result": "skipped", "notes": notes}

	made, created, notes = [], 0, []
	agreement = find_agreement(row.doctor_id)
	course, course_made, note = find_or_make_course(row, agreement, date)
	if course_made:
		made.append(("App Course", course))
		created += 1
	if note:
		notes.append((row.course_id, note))
	student, student_made = find_or_make_student(row, student_key)
	if student_made:
		created += 1

	subscription = frappe.get_doc(
		{
			"doctype": "App Subscription",
			"student": student,
			"course": course,
			"subscription_date": date,
			"source_system": SOURCE,
			"external_id": row.subscription_id,
		}
	)
	subscription.flags.from_import = True
	subscription.insert()
	subscription.submit()
	made.append(("App Subscription", subscription.name))
	return {"result": "inserted", "made": made, "created": created, "notes": notes}


def key(external_id):
	return f"{SOURCE}:{external_id}"


def find_agreement(doctor_id):
	agreements = frappe.get_all(
		"Doctor Agreement",
		filters={"ba_plus_doctor_id": doctor_id, "agreement_type": "App", "docstatus": 1},
		pluck="name",
	)
	if not agreements:
		frappe.throw(
			_("No submitted app agreement has BA Plus doctor id {0}. Write the id on the doctor's app agreement.").format(doctor_id)
		)
	return agreements[0]


def find_or_make_course(row, agreement, date):
	"""(course, made now, a change in BA Plus to list or None)"""
	course = frappe.db.get_value(
		"App Course", {"import_key": key(row.course_id)}, ["name", "course_name", "agreement"], as_dict=True
	)
	if course:
		if course.agreement != agreement:
			frappe.throw(
				_("Course {0} is {1}'s in the ERP, but the file gives doctor {2}. Not changed: check it in BA Plus.").format(
					row.course_id, course.agreement, row.doctor_id
				)
			)
		return course.name, False, course_renamed(row)

	doc = frappe.get_doc(
		{
			"doctype": "App Course",
			"course_name": row.course_name,
			"agreement": agreement,
			"period": term_of(date),
			"source_system": SOURCE,
			"external_id": row.course_id,
		}
	)
	doc.flags.from_import = True
	doc.insert()
	return doc.name, True, None


def course_renamed(row):
	"""The course's name changed in BA Plus: it is the same course (its id), so its students stay on it, and the
	new name is listed, not written over the old one."""
	name = frappe.db.get_value("App Course", {"import_key": key(row.course_id)}, "course_name")
	if name and name != row.course_name:
		return _("Course {0} is named {1} in BA Plus and {2} here; not renamed.").format(row.course_id, row.course_name, name)
	return None


def term_of(date):
	"""The one term the date falls in. BA Plus does not know the ERP's terms; two terms over the same day, or
	none, is for the accountant to sort out in the academic periods, not for the import to guess."""
	terms = frappe.get_all(
		"Academic Period",
		filters={"period_type": "Term", "start_date": ("<=", date), "end_date": (">=", date)},
		pluck="name",
	)
	if len(terms) != 1:
		frappe.throw(
			_("{0} terms hold {1}: {2}. The course's term must be one; check the academic periods.").format(
				len(terms), frappe.format_value(date, {"fieldtype": "Date"}), ", ".join(terms) or _("none")
			)
		)
	return terms[0]


def find_or_make_student(row, student_key):
	# CRM-04: one customer per phone number; the name in the file is used only for a new one.
	customer = customer_with_phone(student_key)
	if customer:
		return customer.name, False
	if not frappe.db.exists("Customer Group", STUDENT_GROUP):
		frappe.throw(_("Customer group {0} is missing, so no new student can be added. Run setup_core.py.").format(STUDENT_GROUP))
	doc = frappe.get_doc(
		{"doctype": "Customer", "customer_name": row.student_name, "customer_group": STUDENT_GROUP, "mobile_no": student_key}
	)
	doc.insert()
	return doc.name, True


def subscription_changes(existing, row, date, student_key):
	changes = []
	if existing.docstatus == 2:
		changes.append(_("cancelled here, still in BA Plus"))
	if frappe.db.get_value("App Course", existing.course, "import_key") != key(row.course_id):
		changes.append(_("course {0}").format(row.course_id))
	if frappe.db.get_value("Customer", existing.student, "custom_phone_key") != student_key:
		changes.append(_("student phone {0}").format(row.student_phone))
	if getdate(existing.subscription_date) != date:
		changes.append(_("date {0}").format(frappe.format_value(date, {"fieldtype": "Date"})))
	return changes
