# The contract between the Windows connector on the library PC (scripts/library_connector) and the ERP: one JSON
# object per document, keyed by the names the Tanmya application itself reads from its procedures' result sets
# (docs/LIBRARY_SQLSERVER_INTEGRATION_ANALYSIS.md, section 5). The physical column names are aliased to these in
# the connector's SELECTs after they are confirmed on site, so nothing here is a guess at a column name: a key
# that is missing fails the document with a clear reason instead of being invented.

SOURCE = "tanmya"

# Each library PC runs its own copy of the Tanmya application on its own database (Db2BDoctorNew on the first
# library's PC, Db2BDoctor on PC1), and their document ids overlap (both start at 1). So every batch names its
# library, a short slug fixed in the PC's config.json, and the id of a mirrored document is
# `tanmya:<library>:<family>:<id>`. Two libraries never share a key; the same library sending twice is one document.
LIBRARY_KEY = "library"
LIBRARY_SLUG = r"^[a-z][a-z0-9_-]{1,29}$"

# Document families and the key names each one uses. "id" is the head's identity in the library's database.
FAMILIES = {
	"stock": {
		"id": "TxtIdRefStock",
		"number": "TxtNumberRefStock",
		"date": "TxtRegDateRefStock",
		"operation_code": "TxtOperationCodeRefStock",
		"operation_name": "TxtOperationNameRefStock",
		"status_code": "TxtStatusCodeRefStock",
		"status_name": "TxtStatusNameRefStock",
		"branch_code": "TxtBranchCodeRefStock",
		"branch_name": "TxtBranchNameRefStock",
		"line_id": "TxtIdRefStockSub",
	},
	"cash_receipt": {
		"id": "TxtIdRefCashReceipt",
		"number": "TxtNumberRefCashReceipt",
		"date": "TxtRegDateRefCashReceipt",
		"operation_code": "TxtOperationCodeRefCashReceipt",
		"operation_name": None,
		"status_code": "TxtStatusCodeRefCashReceipt",
		"status_name": "TxtStatusNameRefCashReceipt",
		"branch_code": "TxtBranchCodeRefCashReceipt",
		"branch_name": "TxtBranchNameRefCashReceipt",
		"line_id": "TxtIdRefCashReceiptSub",
		"kind": "Cash Receipt",
	},
	"cash_payment": {
		"id": "TxtIdRefCashPayment",
		"number": "TxtNumberRefCashPayment",
		"date": "TxtRegDateRefCashPayment",
		"operation_code": "TxtOperationCodeRefCashPayment",
		"operation_name": None,
		"status_code": "TxtStatusCodeRefCashPayment",
		"status_name": "TxtStatusNameRefCashPayment",
		"branch_code": "TxtBranchCodeRefCashPayment",
		"branch_name": "TxtBranchNameRefCashPayment",
		"line_id": "TxtIdRefCashPaymentSub",
		"kind": "Cash Payment",
	},
}

REQUIRED = ("id", "number", "date", "status_code", "branch_code")

# The document kinds a stock document can be (TxtOperationCodeRefStock -> kind, through the connector's
# operation_map filled from TblOperationInfo). Money flows out of the library on the "in" kinds.
STOCK_KINDS = (
	"Retail Sale",
	"Wholesale Sale",
	"Retail Return",
	"Wholesale Return",
	"Purchase",
	"Purchase Return",
	"Opening Balance",
	"Adjustment In",
	"Adjustment Out",
	"Transfer",
	"Price Offer",
)
SALES_KINDS = ("Retail Sale", "Wholesale Sale")
RETURN_KINDS = ("Retail Return", "Wholesale Return")
MONEY_IN_KINDS = SALES_KINDS + ("Purchase Return",)  # the library receives money
MONEY_OUT_KINDS = RETURN_KINDS + ("Purchase",)  # the library pays
ALL_KINDS = STOCK_KINDS + ("Cash Receipt", "Cash Payment", "Other")

# Optional head keys, contract name -> ERP field, for the stock family.
STOCK_HEAD = {
	"TxtStoreCodeFromRefStock": "store_code",
	"TxtStoreNameFromRefStock": "store_name",
	"TxtStoreCodeToRefStock": "store_to_code",
	"TxtStoreNameToRefStock": "store_to_name",
	"TxtCashDeskCodeRefStock": "cash_desk_code",
	"TxtCashDeskNameRefStock": "cash_desk_name",
	"TxtCustomerCodeRefStock": "customer_code",
	"TxtCustomerNameRefStock": "customer_name",
	"TxtCustomerPhone": "customer_phone",
	"TxtVendorCodeRefStock": "vendor_code",
	"TxtVendorNameRefStock": "vendor_name",
	"TxtSalesmanCodeRefStock": "salesman_code",
	"TxtSalesmanNameRefStock": "salesman_name",
	"TxtUserCodeRefStock": "user_code",
	"TxtUserNameRefStock": "user_name",
	"TxtPaymentTypeCodeRefStock": "payment_type_code",
	"TxtPaymentTypeName": "payment_type_name",
	"TxtSalesTypeCode": "sales_type_code",
	"TxtSalesTypeName": "sales_type_name",
	"TxtCashValueRefStock": "cash_value",
	"TxtCreditValueRefStock": "credit_value",
	"TxtVisaValueRefStock": "visa_value",
	"TxtDiscountPercent": "discount_percent",
	"TxtDiscountValue": "discount_value",
	"TxtVatValue": "vat_value",
	"TxtRemarksRefStock": "remarks",
}
CASH_HEAD = {
	"Receipt": {"TxtCashDeskCodeRefCashReceipt": "cash_desk_code", "TxtCashDeskNameRefCashReceipt": "cash_desk_name", "TxtRemarksRefCashReceiptHead": "remarks", "TxtUserCodeRefCashReceipt": "user_code", "TxtUserNameRefCashReceipt": "user_name"},
	"Payment": {"TxtCashDeskCodeRefCashPayment": "cash_desk_code", "TxtCashDeskNameRefCashPayment": "cash_desk_name", "TxtRemarksRefCashPaymentHead": "remarks", "TxtUserCodeRefCashPayment": "user_code", "TxtUserNameRefCashPayment": "user_name"},
}

STOCK_LINE = {
	"TxtIdRefStockSub": "external_id",
	"TxtProductCodeRefStockSub": "product_code",
	"TxtProductNameRefStockSub": "product_name",
	"TxtProductBarCode": "barcode",
	"TxtStoreCodeRefStockSub": "store_code",
	"TxtProductQtyOutRefStockSub": "qty_out",
	"TxtProductQtyInRefStockSub": "qty_in",
	"TxtProductQtyReturnRefStockSub": "qty_return",
	"ChkIsSmallUnit": "is_small_unit",
	"TxtProductUnitCode": "unit_code",
	"TxtProductUnit2Factor": "unit_factor",
	"TxtProductSalesPriceSmallQtyRefStockSub": "price_small",
	"TxtProductSalesPriceSmallQtyBDiscountRefStockSub": "price_small_before_discount",
	"TxtProductSalesPriceBigQtyRefStockSub": "price_big",
	"TxtProductSalesPriceBigQtyBDiscountRefStockSub": "price_big_before_discount",
	"TxtDiscountPercentToRefStockSub": "discount_percent",
	"TxtDiscountValueToRefStockSub": "discount_value",
	"TxtProductTotalValueDownRefStockSub": "value_out",
	"TxtProductTotalValueUpRefStockSub": "value_in",
	"TxtProductVatValueRefStockSub": "vat_value",
	"TxtProductCostPriceRefStockSub": "cost_price",
	"TxtProductCostAvgRefStockSub": "cost_avg",
	"TxtAdjustmentResonCodeRefStockSub": "adjustment_reason_code",
	"TxtDoctorCode": "doctor_code",
	"TxtDoctorName": "doctor_name",
}
CASH_LINE = {
	"Receipt": {"TxtIdRefCashReceiptSub": "external_id", "TxtAccNumberLevel5CodeRefCashReceiptSub": "account_l5_code", "TxtAccNumberLevel5NameRefCashReceiptSub": "account_l5_name", "TxtAccNumberLevel6CodeRefCashReceiptSub": "account_l6_code", "TxtAccNumberLevel6NameRefCashReceiptSub": "account_l6_name", "TxtAccNumberLevel7CodeRefCashReceiptSub": "account_l7_code", "TxtAccNumberLevel7NameRefCashReceiptSub": "account_l7_name", "TxtDebitValueRefCashReceiptSub": "debit", "TxtCreditValueRefCashReceiptSub": "credit", "TxtRemarksRefCashReceiptSub": "remarks"},
	"Payment": {"TxtIdRefCashPaymentSub": "external_id", "TxtAccNumberLevel5CodeRefCashPaymentSub": "account_l5_code", "TxtAccNumberLevel5NameRefCashPaymentSub": "account_l5_name", "TxtAccNumberLevel6CodeRefCashPaymentSub": "account_l6_code", "TxtAccNumberLevel6NameRefCashPaymentSub": "account_l6_name", "TxtAccNumberLevel7CodeRefCashPaymentSub": "account_l7_code", "TxtAccNumberLevel7NameRefCashPaymentSub": "account_l7_name", "TxtDebitValueRefCashPaymentSub": "debit", "TxtCreditValueRefCashPaymentSub": "credit", "TxtRemarksRefCashPaymentSub": "remarks"},
}
