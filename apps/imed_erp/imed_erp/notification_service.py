# Unified notification service (CORE-10): one entry point every module uses to notify people.
#
#   from imed_erp.notification_service import notify
#   notify("doctor_settlement_due", ["accountant@imed.local"], {"doctor": "Dr. X", "amount": "EGP 1,500.00"})
#
# An event has a subject and a message (Jinja templates) and the channels it goes out on by default.
# Channels:
#   system    in-app notification (bell icon), works now
#   email     through the site's outgoing Email Account, works once one is configured
#   whatsapp  through CallMeBot (free, unofficial): it only writes to a person who allowed it from their own
#             WhatsApp and got a key back. Who that is lives in site_config.json, never in the code:
#               "imed_whatsapp_recipients": {"owner@imed.local": {"phone": "+2010xxxxxxxx", "apikey": "123456"}}
#             A user who is not listed there gets nothing on this channel. The message leaves after the
#             transaction commits, from a background job, so a slow or failing CallMeBot never holds up or
#             breaks what the user was doing.
#   telegram  through a Telegram bot (official and free). The bot is made once with @BotFather, which gives its
#             token; a person gets messages after pressing Start in the bot. Both live in site_config.json:
#               "imed_telegram_bot_token": "123456:ABC...",
#               "imed_telegram_chats": {"owner@imed.local": "987654321"}
#             The chat id of whoever pressed Start:  bench --site <site> execute imed_erp.notification_service.telegram_chats
#             A user who is not listed gets nothing on this channel. Sent after the commit, from a background
#             job, like WhatsApp.
#   sms       not integrated yet: the adapter only logs what it would send
#
# To add an event, add it to EVENTS. To integrate a provider, fill in its adapter; nothing else changes.

import frappe
import requests
from frappe import _
from frappe.utils.jinja import render_template

WHATSAPP_URL = "https://api.callmebot.com/whatsapp.php"
WHATSAPP_TIMEOUT = 15  # seconds
TELEGRAM_URL = "https://api.telegram.org/bot{token}/{method}"
TELEGRAM_TIMEOUT = 15  # seconds

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
	# Expenses (EXP-05/06). The wording is made and translated by the module, so the template passes it on.
	"expense_reminder": {
		"subject": "{{ subject }}",
		"message": "{{ subject }}",
		"channels": ["system"],
	},
	"expense_approval": {
		"subject": "{{ subject }}",
		"message": "{{ subject }}",
		"channels": ["system"],
	},
	# Branch requests from the main warehouse (imederp/material_issue.py); worded and translated there.
	"stock_request_approval": {
		"subject": "{{ subject }}",
		"message": "{{ subject }}",
		"channels": ["system"],
	},
	"reorder_level_reached": {
		"subject": "Reorder: {{ item }} at {{ warehouse }}",
		"message": "{{ item }} ({{ item_code }}) at {{ warehouse }} is down to {{ qty }} {{ uom }}; "
		"its reorder level there is {{ level }}. ({{ voucher }})",
		"channels": ["system"],
	},
	# Paper sold for printing that the store did not show yet (imederp/paper_use.py). Worded by the module.
	"paper_issue_pending": {
		"subject": "{{ subject }}",
		"message": "{{ subject }}",
		"channels": ["system"],
	},
	# For the owner, on their phone only: Telegram and WhatsApp, whichever is set up (imederp/owner_alerts.py).
	"owner_stock_request": {
		"subject": "New stock request for {{ warehouse }}",
		"message": "New stock request for {{ warehouse }} ({{ request }}): {{ items }}",
		"channels": ["telegram", "whatsapp"],
	},
	# The day's revenue and bookings; worded and translated by the module.
	"owner_daily_summary": {
		"subject": "{{ subject }}",
		"message": "{{ message }}",
		"channels": ["telegram", "whatsapp"],
	},
	"period_closed": {
		"subject": "Accounting period {{ period }} closed",
		"message": "Posting dated {{ start }} to {{ end }} is now blocked.",
		"channels": ["system", "email"],
	},
}


def notify(event, users, context=None, channels=None, document=None):
	"""Send `event` to each user (User IDs) on `channels` (default: the event's own channels).

	`document` is an optional (doctype, name): the in-app notification opens it, and the same notification
	about the same document is not sent twice to a user.

	Returns {channel: [users it was sent to]}. A failing channel is logged and does not stop the others.
	"""
	spec = EVENTS[event]
	context = context or {}
	# The templates are translated before they are filled in (translations/ar.csv has them with their
	# {{ placeholders }}), so the people notified read them in the site's language.
	subject = render_template(_(spec["subject"]), context)
	message = render_template(_(spec["message"]), context)

	sent = {}
	for channel in channels or spec["channels"]:
		try:
			sent[channel] = ADAPTERS[channel](users, subject, message, event, document)
		except Exception:
			frappe.log_error(title=f"Notification {event} failed on {channel}")
			sent[channel] = []
	return sent


def _system(users, subject, message, event, document=None):
	document_type, document_name = document or (None, None)
	sent = []
	for user in users:
		if document and frappe.db.exists(
			"Notification Log",
			{"for_user": user, "subject": subject, "document_type": document_type, "document_name": document_name},
		):
			continue
		frappe.get_doc(
			{
				"doctype": "Notification Log",
				"for_user": user,
				"type": "Alert",
				"subject": subject,
				"email_content": message,
				"document_type": document_type,
				"document_name": document_name,
			}
		).insert(ignore_permissions=True)
		sent.append(user)
	return sent


def _email(users, subject, message, event, document=None):
	recipients = [e for e in (frappe.db.get_value("User", u, "email") for u in users) if e]
	if recipients:
		frappe.sendmail(recipients=recipients, subject=subject, message=message)
	return recipients


def whatsapp_recipient(user):
	"""The user's {"phone", "apikey"} from the site's configuration, or None when they have not been set up."""
	recipient = (frappe.conf.get("imed_whatsapp_recipients") or {}).get(user) or {}
	return recipient if recipient.get("phone") and recipient.get("apikey") else None


def _whatsapp(users, subject, message, event, document=None):
	queued = []
	for user in users:
		if not whatsapp_recipient(user):
			continue
		# The job is given the user, not the key: the key stays in the configuration and out of the queue.
		frappe.enqueue(
			"imed_erp.notification_service.send_whatsapp",
			queue="short",
			enqueue_after_commit=True,
			user=user,
			text=message,
		)
		queued.append(user)
	return queued


def send_whatsapp(user, text):
	"""One message to one user through CallMeBot. True when it accepted it; a failure is logged, never raised."""
	recipient = whatsapp_recipient(user)
	if not recipient:
		return False
	try:
		response = requests.get(
			WHATSAPP_URL,
			params={"phone": recipient["phone"], "text": text, "apikey": recipient["apikey"]},
			timeout=WHATSAPP_TIMEOUT,
		)
		ok, detail = response.status_code == 200, f"HTTP {response.status_code}: {response.text[:300]}"
	except requests.RequestException as e:
		# Only the kind of failure: the exception's own text carries the address, and the key is in it.
		ok, detail = False, type(e).__name__
	if not ok:
		frappe.log_error(title="WhatsApp message not sent", message=f"{user}: {detail}".replace(recipient["apikey"], "***"))
	return ok


def telegram_chat(user):
	"""The user's Telegram chat id, or None when the bot or the user has not been set up."""
	chat = (frappe.conf.get("imed_telegram_chats") or {}).get(user)
	return str(chat) if chat and frappe.conf.get("imed_telegram_bot_token") else None


def _telegram(users, subject, message, event, document=None):
	queued = []
	for user in users:
		if not telegram_chat(user):
			continue
		frappe.enqueue(
			"imed_erp.notification_service.send_telegram",
			queue="short",
			enqueue_after_commit=True,
			user=user,
			text=message,
		)
		queued.append(user)
	return queued


def telegram_call(method, payload):
	"""(ok, result or reason) of one call to the bot's API. The token is in the address, so nothing of the
	request is ever put in the reason."""
	token = frappe.conf.get("imed_telegram_bot_token")
	if not token:
		return False, "imed_telegram_bot_token is not set"
	try:
		response = requests.post(
			TELEGRAM_URL.format(token=token, method=method), json=payload, timeout=TELEGRAM_TIMEOUT
		)
		body = response.json()
	except requests.RequestException as e:
		return False, type(e).__name__
	except ValueError:
		return False, f"HTTP {response.status_code}"
	if not body.get("ok"):
		return False, f"HTTP {response.status_code}: {body.get('description')}".replace(token, "***")
	return True, body.get("result")


def send_telegram(user, text):
	"""One message to one user from the bot. True when Telegram accepted it; a failure is logged, never raised."""
	chat = telegram_chat(user)
	if not chat:
		return False
	ok, detail = telegram_call("sendMessage", {"chat_id": chat, "text": text})
	if not ok:
		frappe.log_error(title="Telegram message not sent", message=f"{user}: {detail}")
	return ok


def telegram_chats():
	"""Who wrote to the bot lately (pressed Start), to copy a chat id into imed_telegram_chats:
	[{"chat_id", "name", "username"}]. Telegram keeps these for about a day."""
	ok, updates = telegram_call("getUpdates", {})
	if not ok:
		frappe.throw(str(updates))
	chats = {}
	for update in updates or []:
		chat = (update.get("message") or update.get("my_chat_member") or {}).get("chat") or {}
		if chat.get("id"):
			name = chat.get("title") or " ".join(filter(None, [chat.get("first_name"), chat.get("last_name")]))
			chats[chat["id"]] = {"chat_id": chat["id"], "name": name, "username": chat.get("username")}
	return list(chats.values())


def _not_integrated(channel):
	def adapter(users, subject, message, event, document=None):
		numbers = [frappe.db.get_value("User", u, "mobile_no") for u in users]
		frappe.logger("imed_notifications").info(
			f"{channel} not integrated yet; would send {event!r} to {numbers}: {subject}"
		)
		return []

	return adapter


ADAPTERS = {
	"system": _system,
	"email": _email,
	"whatsapp": _whatsapp,
	"telegram": _telegram,
	"sms": _not_integrated("sms"),
}
