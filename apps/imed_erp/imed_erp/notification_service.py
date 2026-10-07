# Unified notification service (CORE-10): one entry point every module uses to notify people.
#
#   from imed_erp.notification_service import notify
#   notify("doctor_settlement_due", ["accountant@imed.local"], {"doctor": "Dr. X", "amount": "EGP 1,500.00"})
#
# An event has a subject and a message (Jinja templates) and the channels it goes out on by default.
# Channels:
#   system    in-app notification (bell icon), works now
#   email     through the site's outgoing Email Account, works once one is configured
#   whatsapp  not integrated yet: the adapter only logs what it would send
#   sms       not integrated yet: the adapter only logs what it would send
#
# To add an event, add it to EVENTS. To integrate a provider, fill in its adapter; nothing else changes.

import frappe
from frappe.utils.jinja import render_template

# Templates are placeholders until each module defines its real wording.
EVENTS = {
	"test": {
		"subject": "Test notification",
		"message": "This is a test of the notification service. {{ note or '' }}",
		"channels": ["system"],
	},
	"booking_reminder": {
		"subject": "Booking reminder: {{ booking }}",
		"message": "Reminder: {{ booking }} on {{ date }}.",
		"channels": ["system", "whatsapp"],
	},
	"doctor_settlement_due": {
		"subject": "Settlement due: {{ doctor }}",
		"message": "The settlement for {{ doctor }} is due: {{ amount }}.",
		"channels": ["system", "email"],
	},
	"low_paper_stock": {
		"subject": "Low paper stock at {{ warehouse }}",
		"message": "{{ item }} at {{ warehouse }} is down to {{ qty }}.",
		"channels": ["system"],
	},
	"reorder_level_reached": {
		"subject": "Reorder: {{ item }} at {{ warehouse }}",
		"message": "{{ item }} ({{ item_code }}) at {{ warehouse }} is down to {{ qty }} {{ uom }}; "
		"its reorder level there is {{ level }}. ({{ voucher }})",
		"channels": ["system"],
	},
	"period_closed": {
		"subject": "Accounting period {{ period }} closed",
		"message": "Posting dated {{ start }} to {{ end }} is now blocked.",
		"channels": ["system", "email"],
	},
}


def notify(event, users, context=None, channels=None):
	"""Send `event` to each user (User IDs) on `channels` (default: the event's own channels).

	Returns {channel: [users it was sent to]}. A failing channel is logged and does not stop the others.
	"""
	spec = EVENTS[event]
	context = context or {}
	subject = render_template(spec["subject"], context)
	message = render_template(spec["message"], context)

	sent = {}
	for channel in channels or spec["channels"]:
		try:
			sent[channel] = ADAPTERS[channel](users, subject, message, event)
		except Exception:
			frappe.log_error(title=f"Notification {event} failed on {channel}")
			sent[channel] = []
	return sent


def _system(users, subject, message, event):
	for user in users:
		frappe.get_doc(
			{
				"doctype": "Notification Log",
				"for_user": user,
				"type": "Alert",
				"subject": subject,
				"email_content": message,
			}
		).insert(ignore_permissions=True)
	return list(users)


def _email(users, subject, message, event):
	recipients = [e for e in (frappe.db.get_value("User", u, "email") for u in users) if e]
	if recipients:
		frappe.sendmail(recipients=recipients, subject=subject, message=message)
	return recipients


def _not_integrated(channel):
	def adapter(users, subject, message, event):
		numbers = [frappe.db.get_value("User", u, "mobile_no") for u in users]
		frappe.logger("imed_notifications").info(
			f"{channel} not integrated yet; would send {event!r} to {numbers}: {subject}"
		)
		return []

	return adapter


ADAPTERS = {
	"system": _system,
	"email": _email,
	"whatsapp": _not_integrated("whatsapp"),
	"sms": _not_integrated("sms"),
}
