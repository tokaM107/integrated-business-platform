# The library connector's contract, mapping and receiving end, on mock documents shaped like the Tanmya app's
# result sets (docs/LIBRARY_SQLSERVER_INTEGRATION_ANALYSIS.md). No SQL Server is touched: the connector's job
# (reading) is simulated by the batch; the ERP's job (mapping, logging, idempotency) is what is tested.
#
#   bench --site frontend run-tests --module imed_erp.imederp.test_library_sync
import copy

import frappe
from frappe.tests import IntegrationTestCase

from imed_erp.imederp.library_sync import contract as c
from imed_erp.imederp.library_sync import mappers, sync

def cost_center(name):
	return frappe.get_all("Cost Center", filters={"cost_center_name": name}, pluck="name")[0]


def settings():
	"""What the connector sends with every batch (its config.json); the cost centers are the site's own."""
	return {
		"branch_map": {"1": cost_center("مكتبة الأزاريطة"), "2": cost_center("مكتبة المواساة")},
		"operation_map": {"11": "Retail Sale", "12": "Wholesale Sale", "21": "Retail Return", "31": "Purchase"},
		"issued_status_codes": ["2"],
		"cancelled_status_codes": ["3"],
	}


def sale(external_id="90001", status="2", operation="11", branch="1", lines=None, number="A-1001"):
	return {
		"_family": "stock",
		"TxtIdRefStock": external_id,
		"TxtNumberRefStock": number,
		"TxtRegDateRefStock": "2026-10-24 18:05:00",
		"TxtOperationCodeRefStock": operation,
		"TxtOperationNameRefStock": "فاتورة مبيعات تجزئة",
		"TxtStatusCodeRefStock": status,
		"TxtStatusNameRefStock": "مصدر" if status == "2" else "معلق" if status == "1" else "ملغي",
		"TxtBranchCodeRefStock": branch,
		"TxtBranchNameRefStock": "الأزاريطة",
		"TxtCashDeskCodeRefStock": "1",
		"TxtCustomerCodeRefStock": "77",
		"TxtCustomerNameRefStock": "عميل نقدي",
		"TxtPaymentTypeCodeRefStock": "1",
		"TxtCashValueRefStock": "150",
		"TxtCreditValueRefStock": "0",
		"TxtVisaValueRefStock": "0",
		"TxtDiscountValue": "0",
		"TxtVatValue": "0",
		"lines": lines
		if lines is not None
		else [
			{"TxtIdRefStockSub": "500001", "TxtIdRefStock": external_id, "TxtProductCodeRefStockSub": "P-1", "TxtProductNameRefStockSub": "كتاب باثولوجي", "TxtProductQtyOutRefStockSub": "2", "TxtProductQtyInRefStockSub": "0", "TxtProductSalesPriceSmallQtyRefStockSub": "50", "TxtProductTotalValueDownRefStockSub": "100", "TxtDoctorCode": "D7", "TxtDoctorName": "د. أحمد"},
			{"TxtIdRefStockSub": "500002", "TxtIdRefStock": external_id, "TxtProductCodeRefStockSub": "P-2", "TxtProductNameRefStockSub": "ملزمة", "TxtProductQtyOutRefStockSub": "1", "TxtProductQtyInRefStockSub": "0", "TxtProductSalesPriceSmallQtyRefStockSub": "50", "TxtProductTotalValueDownRefStockSub": "50"},
		],
	}


def receipt(external_id="70001"):
	return {
		"_family": "cash_receipt",
		"TxtIdRefCashReceipt": external_id,
		"TxtNumberRefCashReceipt": "R-5",
		"TxtRegDateRefCashReceipt": "2026-10-24",
		"TxtStatusCodeRefCashReceipt": "2",
		"TxtStatusNameRefCashReceipt": "مصدر",
		"TxtBranchCodeRefCashReceipt": "2",
		"TxtCashDeskCodeRefCashReceipt": "1",
		"lines": [{"TxtIdRefCashReceiptSub": "1", "TxtAccNumberLevel7CodeRefCashReceiptSub": "4-1-1-1-7", "TxtAccNumberLevel7NameRefCashReceiptSub": "عميل", "TxtDebitValueRefCashReceiptSub": "300", "TxtCreditValueRefCashReceiptSub": "0"}],
	}


class TestLibraryMappers(IntegrationTestCase):
	def test_a_retail_sale_maps_to_its_fields_and_sums_its_lines(self):
		fields, notes = mappers.map_document("stock", sale(), settings())
		self.assertEqual((fields["document_kind"], fields["number"], fields["is_final"], fields["is_cancelled"], fields["cost_center"]), ("Retail Sale", "A-1001", 1, 0, cost_center("مكتبة الأزاريطة")))
		self.assertEqual((fields["total"], fields["qty_total"], fields["money_direction"], len(fields["lines"])), (150.0, 3.0, "In", 2))
		self.assertEqual((fields["lines"][0]["product_code"], fields["lines"][0]["qty"], fields["lines"][0]["line_total"], fields["lines"][0]["doctor_name"]), ("P-1", 2.0, 100.0, "د. أحمد"))
		self.assertEqual(fields["import_key"], "tanmya:stock:90001")
		self.assertEqual(notes, [])

	def test_a_held_and_a_cancelled_document_are_not_final(self):
		held, _ = mappers.map_document("stock", sale(status="1"), settings())
		cancelled, _ = mappers.map_document("stock", sale(status="3"), settings())
		self.assertEqual((held["is_final"], held["is_cancelled"], cancelled["is_final"], cancelled["is_cancelled"]), (0, 0, 0, 1))

	def test_an_unknown_operation_code_is_other_and_noted_never_guessed(self):
		fields, notes = mappers.map_document("stock", sale(operation="99"), settings())
		self.assertEqual(fields["document_kind"], "Other")
		self.assertIn("operation code '99'", notes[0])

	def test_an_unmapped_branch_is_noted(self):
		fields, notes = mappers.map_document("stock", sale(branch="9"), settings())
		self.assertIsNone(fields["cost_center"])
		self.assertTrue(any("branch code '9'" in n for n in notes))

	def test_a_missing_required_key_fails_with_its_name(self):
		document = sale()
		del document["TxtRegDateRefStock"]
		with self.assertRaises(mappers.MappingError) as ctx:
			mappers.map_document("stock", document, settings())
		self.assertIn("TxtRegDateRefStock", str(ctx.exception))

	def test_a_purchase_values_its_lines_on_the_in_side(self):
		lines = [{"TxtIdRefStockSub": "1", "TxtProductCodeRefStockSub": "P-9", "TxtProductQtyInRefStockSub": "10", "TxtProductTotalValueUpRefStockSub": "400", "TxtProductCostPriceRefStockSub": "40"}]
		fields, _ = mappers.map_document("stock", sale(operation="31", lines=lines), settings())
		self.assertEqual((fields["document_kind"], fields["total"], fields["qty_total"], fields["money_direction"]), ("Purchase", 400.0, 10.0, "Out"))

	def test_a_cash_receipt_maps_its_account_rows(self):
		fields, notes = mappers.map_document("cash_receipt", receipt(), settings())
		self.assertEqual((fields["document_kind"], fields["total"], fields["money_direction"], fields["lines"][0]["account_l7_code"], fields["cost_center"]), ("Cash Receipt", 300.0, "In", "4-1-1-1-7", cost_center("مكتبة المواساة")))

	def test_the_payload_hash_ignores_key_order_and_connector_bookkeeping(self):
		a = sale()
		b = dict(reversed(list(a.items())))
		b["_family"] = "stock"
		b["_read_at"] = "later"
		self.assertEqual(mappers.payload_hash(a), mappers.payload_hash(b))
		changed = sale()
		changed["TxtCashValueRefStock"] = "151"
		self.assertNotEqual(mappers.payload_hash(a), mappers.payload_hash(changed))


class TestLibraryReceive(IntegrationTestCase):
	def setUp(self):
		frappe.db.savepoint("library_test")

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback(save_point="library_test")

	def batch(self, *documents):
		return frappe._dict(settings(), source="tanmya", read_at="2026-10-26 12:00", documents=list(documents))

	def counts(self, log):
		return (log.status, log.rows_read, log.inserted, log.updated, log.skipped, log.changed, log.failed)

	def doc(self, key):
		return frappe.get_doc("Library Sales Document", {"import_key": key})

	def test_a_batch_is_logged_and_its_documents_mirrored(self):
		log = sync.import_batch(self.batch(sale(), receipt()))
		self.assertEqual((log.source_system, self.counts(log)), ("tanmya", ("Completed", 2, 2, 0, 0, 0, 0)))
		doc = self.doc("tanmya:stock:90001")
		self.assertEqual((doc.document_kind, doc.total, len(doc.lines), doc.lines[0].product_name, doc.is_final), ("Retail Sale", 150.0, 2, "كتاب باثولوجي", 1))
		self.assertEqual(self.doc("tanmya:cash_receipt:70001").document_kind, "Cash Receipt")
		# nothing financial came of it
		self.assertEqual((frappe.db.count("Sales Invoice", {"creation": (">=", log.started_at)}), frappe.db.count("Payment Entry", {"creation": (">=", log.started_at)}), frappe.db.count("Journal Entry", {"creation": (">=", log.started_at)})), (0, 0, 0))

	def test_the_same_batch_again_changes_nothing(self):
		sync.import_batch(self.batch(sale()))
		log = sync.import_batch(self.batch(sale()))
		self.assertEqual(self.counts(log), ("Completed", 1, 0, 0, 1, 0, 0))
		self.assertEqual(frappe.db.count("Library Sales Document", {"import_key": "tanmya:stock:90001"}), 1)

	def test_a_document_changed_in_the_library_is_updated_and_listed(self):
		sync.import_batch(self.batch(sale(status="1")))  # held
		self.assertEqual(self.doc("tanmya:stock:90001").is_final, 0)
		log = sync.import_batch(self.batch(sale(status="2")))  # issued later
		self.assertEqual(self.counts(log), ("Completed with Errors", 1, 0, 1, 0, 1, 0))
		self.assertEqual([r.kind for r in log.errors], ["Changed in Source"])
		doc = self.doc("tanmya:stock:90001")
		self.assertEqual((doc.is_final, len(doc.lines)), (1, 2))
		# then cancelled there: kept, marked, never deleted
		sync.import_batch(self.batch(sale(status="3")))
		doc = self.doc("tanmya:stock:90001")
		self.assertEqual((doc.is_final, doc.is_cancelled), (0, 1))

	def test_a_bad_document_fails_alone(self):
		bad = sale(external_id="90002")
		del bad["TxtNumberRefStock"]
		log = sync.import_batch(self.batch(sale(), bad))
		self.assertEqual(self.counts(log), ("Completed with Errors", 2, 1, 0, 0, 0, 1))
		self.assertIn("TxtNumberRefStock", log.errors[0].reason)
		self.assertEqual(frappe.db.count("Library Sales Document", {"import_key": "tanmya:stock:90002"}), 0)

	def test_an_unknown_operation_is_kept_as_other_and_listed_for_review(self):
		log = sync.import_batch(self.batch(sale(operation="99")))
		self.assertEqual((self.counts(log)[2], [r.kind for r in log.errors]), (1, ["Needs Review"]))
		self.assertEqual(self.doc("tanmya:stock:90001").document_kind, "Other")

	def test_a_mirrored_document_is_not_changed_here(self):
		sync.import_batch(self.batch(sale()))
		doc = self.doc("tanmya:stock:90001")
		doc.total = 1
		self.assertRaises(frappe.ValidationError, doc.save)
		self.assertRaises(frappe.ValidationError, doc.delete)

	def test_the_endpoint_is_for_the_accounts_only(self):
		frappe.set_user("gilan@imed.local")
		self.assertRaises(frappe.PermissionError, sync.receive, self.batch(sale()))

	def test_the_status_report_shows_the_source(self):
		sync.import_batch(self.batch(sale()))
		from imed_erp.imederp.report.integration_status.integration_status import get_data

		[row] = [r for r in get_data() if r["system"] == "tanmya"]
		self.assertEqual((row["status"], row["inserted"]), ("Completed", 1))
