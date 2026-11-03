# Read-only: the printing and copying sales whose paper issue is still a draft (imederp/paper_use.py saves the
# issue as a draft when the store shows fewer sheets than were sold). Until the draft is submitted the sale's
# revenue is in the books but its paper cost and stock movement are not. Nothing is written, submitted, dated or
# deleted here: the procedure to settle them is in docs/release/release-candidate-2026-11-02.md.
#
#   docker exec frappe_docker-backend-1 bench --site <site> execute imed_erp.setup.paper_drafts_report.run

import frappe
from frappe.utils import date_diff, flt, today

PAPER = "A4-PAPER"


def drafts():
	"""Each draft paper issue that names a sale, with the sale's state and the store's sheets now."""
	return frappe.db.sql(
		"""select se.name as issue, se.creation as issue_made, si.name as sale, si.docstatus as sale_docstatus,
			si.posting_date as sale_date, si.company, sed.s_warehouse as store, sed.qty as sheets,
			coalesce(bin.actual_qty, 0) as sheets_in_store_now
		from `tabStock Entry` se
		join `tabStock Entry Detail` sed on sed.parent = se.name and sed.item_code = %(paper)s
		left join `tabSales Invoice` si on si.name = se.sales_invoice_no
		left join `tabBin` bin on bin.item_code = sed.item_code and bin.warehouse = sed.s_warehouse
		where se.docstatus = 0 and coalesce(se.sales_invoice_no, '') != ''
		order by si.posting_date, se.name""",
		{"paper": PAPER},
		as_dict=True,
	)


def run():
	rows = drafts()
	completed = [r for r in rows if r.sale_docstatus == 1]
	orphans = [r for r in rows if r.sale_docstatus != 1]
	print(f"site {frappe.local.site}: {len(rows)} draft paper issue(s) naming a sale")
	print(f"  completed sales still waiting for their paper: {len(completed)}, {flt(sum(r.sheets for r in completed))} sheets")
	for r in completed:
		print(
			f"    {r.sale} of {r.sale_date} ({date_diff(today(), r.sale_date)} days), issue {r.issue}: {flt(r.sheets)} sheets "
			f"from {r.store}, {flt(r.sheets_in_store_now)} there now"
		)
	print(f"  drafts whose sale is not submitted (cancelled or draft): {len(orphans)}")
	for r in orphans:
		print(f"    issue {r.issue} names {r.sale} (docstatus {r.sale_docstatus})")
	return {"completed": len(completed), "orphans": len(orphans)}
