import frappe

# ---------- Printer Reading ----------
if not frappe.db.exists("DocType", "Printer Reading"):
    frappe.get_doc({
        "doctype": "DocType", "name": "Printer Reading", "module": "ImedERP",
        "is_submittable": 1, "autoname": "hash",
        "fields": [
            {"fieldname": "branch", "label": "Cost Center", "fieldtype": "Link", "options": "Cost Center", "reqd": 1, "in_list_view": 1},
            {"fieldname": "machine", "label": "Machine", "fieldtype": "Data", "reqd": 1, "in_list_view": 1},
            {"fieldname": "reading_date", "label": "Date", "fieldtype": "Date", "reqd": 1, "in_list_view": 1},
            {"fieldname": "opening_reading", "label": "Opening", "fieldtype": "Int", "reqd": 1},
            {"fieldname": "closing_reading", "label": "Closing", "fieldtype": "Int", "reqd": 1},
            {"fieldname": "consumed", "label": "Consumed Sheets", "fieldtype": "Int", "read_only": 1, "in_list_view": 1},
            {"fieldname": "sold_sheets", "label": "Sold Sheets", "fieldtype": "Int"},
            {"fieldname": "variance", "label": "Variance", "fieldtype": "Int", "read_only": 1},
        ],
        "permissions": [{"role": "System Manager", "read": 1, "write": 1, "create": 1, "submit": 1, "cancel": 1}],
    }).insert()
    print("created: Printer Reading")

# ---------- App Subscription ----------
if not frappe.db.exists("DocType", "App Subscription"):
    frappe.get_doc({
        "doctype": "DocType", "name": "App Subscription", "module": "ImedERP",
        "is_submittable": 1, "autoname": "hash",
        "fields": [
            {"fieldname": "student", "label": "Student", "fieldtype": "Link", "options": "Customer", "reqd": 1, "in_list_view": 1},
            {"fieldname": "agreement", "label": "Doctor Agreement", "fieldtype": "Link", "options": "Doctor Agreement", "reqd": 1},
            {"fieldname": "course", "label": "Course", "fieldtype": "Data", "in_list_view": 1},
            {"fieldname": "period", "label": "Period", "fieldtype": "Link", "options": "Academic Period"},
            {"fieldname": "subscription_date", "label": "Date", "fieldtype": "Date", "reqd": 1},
            {"fieldname": "total_paid", "label": "Total Paid by Student", "fieldtype": "Currency", "reqd": 1},
            {"fieldname": "platform_fee", "label": "Platform Fee (Due from Doctor)", "fieldtype": "Currency", "reqd": 1, "in_list_view": 1},
            {"fieldname": "course_amount", "label": "Course Amount (Doctor)", "fieldtype": "Currency", "read_only": 1},
        ],
        "permissions": [{"role": "System Manager", "read": 1, "write": 1, "create": 1, "submit": 1, "cancel": 1}],
    }).insert()
    print("created: App Subscription")

frappe.db.commit()

# ---------- الحسابات التلقائية ----------
import os

def write_controller(doctype_folder, class_name, body):
    path = frappe.get_app_path("imed_erp", "imederp", "doctype", doctype_folder, doctype_folder + ".py")
    code = f'''import frappe
from frappe.model.document import Document


class {class_name}(Document):
{body}
'''
    with open(path, "w") as f:
        f.write(code)
    print("controller written:", path)


# تسعير الإصدار: السعر = التكلفة + نصيب المالك + نصيب الطبيب
write_controller("book_edition", "BookEdition", '''    def validate(self):
        base = (self.unit_cost or 0) + (self.owner_share or 0) + (self.doctor_share or 0)
        self.calculated_price = base
        if not self.selling_price:
            self.selling_price = base
        self.rounding_diff = (self.selling_price or 0) - base
''')

# عداد الورق: المستهلك والفرق
write_controller("printer_reading", "PrinterReading", '''    def validate(self):
        self.consumed = (self.closing_reading or 0) - (self.opening_reading or 0)
        if self.consumed < 0:
            frappe.throw("Closing reading cannot be less than opening reading")
        self.variance = self.consumed - (self.sold_sheets or 0)
''')

# اشتراك التطبيق: قيمة الكورس = المدفوع - رسوم المنصة
write_controller("app_subscription", "AppSubscription", '''    def validate(self):
        self.course_amount = (self.total_paid or 0) - (self.platform_fee or 0)
        if self.course_amount < 0:
            frappe.throw("Platform fee cannot exceed total paid")
''')

print("\\nDone. Now run migrate and restart.")