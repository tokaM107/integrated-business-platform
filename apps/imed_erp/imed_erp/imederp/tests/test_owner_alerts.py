# Copyright (c) 2026, toka mohamed and Contributors
# See license.txt

# The owner's messages (imederp/owner_alerts.py) and the Telegram and WhatsApp channels of the notification
# service. Nothing here reaches Telegram or CallMeBot: the HTTP call and the queue are replaced. Every test is rolled back.
#
# Run:
#   bench --site frontend run-tests --module imed_erp.imederp.tests.test_owner_alerts

from collections import Counter
from unittest.mock import MagicMock, patch

import frappe
import requests
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, nowdate

from imed_erp import notification_service
from imed_erp.imederp import material_issue, owner_alerts
from imed_erp.imederp.tests.test_material_issue import AZARITA_STORE, CARTON, COMPANY, MAWASAH_STORE, PAPER, SARA, as_user

OWNER_USER = "test-owner-alerts@imed.local"
KEY = "654321"
TOKEN = "111222:SECRET-TOKEN"
CHAT = "987654321"


class IntegrationTestOwnerAlerts(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		frappe.db.savepoint("owner_alerts_test")
		frappe.conf.imed_whatsapp_recipients = {OWNER_USER: {"phone": "+201000000000", "apikey": KEY}}

	def tearDown(self):
		frappe.set_user("Administrator")
		for key in ("imed_whatsapp_recipients", "imed_telegram_bot_token", "imed_telegram_chats"):
			frappe.conf.pop(key, None)
		frappe.db.rollback(save_point="owner_alerts_test")

	# ---------- the channel ----------
	def test_only_listed_users_are_queued_and_the_key_stays_out_of_the_queue(self):
		with patch.object(frappe, "enqueue") as enqueue:
			sent = notification_service.notify(
				"owner_daily_summary", [OWNER_USER, SARA], {"subject": "s", "message": "سطر ١\nسطر ٢"}
			)
		self.assertEqual(sent, {"telegram": [], "whatsapp": [OWNER_USER]})
		enqueue.assert_called_once()
		kwargs = enqueue.call_args.kwargs
		self.assertEqual((kwargs["user"], kwargs["text"]), (OWNER_USER, "سطر ١\nسطر ٢"))
		self.assertTrue(kwargs["enqueue_after_commit"])
		self.assertNotIn(KEY, str(enqueue.call_args))

	def test_nobody_listed_sends_nothing(self):
		frappe.conf.pop("imed_whatsapp_recipients", None)
		with patch.object(frappe, "enqueue") as enqueue:
			sent = notification_service.notify("owner_daily_summary", [OWNER_USER], {"subject": "s", "message": "m"})
		self.assertEqual(sent, {"telegram": [], "whatsapp": []})
		enqueue.assert_not_called()

	def test_send_calls_callmebot_with_the_users_phone_and_key(self):
		with patch.object(requests, "get", return_value=MagicMock(status_code=200, text="Message queued")) as get:
			self.assertTrue(notification_service.send_whatsapp(OWNER_USER, "مرحبا"))
		self.assertEqual(get.call_args.args, (notification_service.WHATSAPP_URL,))
		self.assertEqual(get.call_args.kwargs["params"], {"phone": "+201000000000", "text": "مرحبا", "apikey": KEY})
		self.assertFalse(notification_service.send_whatsapp(SARA, "مرحبا"))  # not listed

	def test_a_failure_is_logged_without_the_key_and_not_raised(self):
		failures = (
			{"return_value": MagicMock(status_code=203, text=f"APIKey {KEY} is invalid")},
			{"side_effect": requests.ConnectionError(f"https://x/?apikey={KEY}")},
		)
		for failure in failures:
			with patch.object(requests, "get", **failure), patch.object(frappe, "log_error") as log_error:
				self.assertFalse(notification_service.send_whatsapp(OWNER_USER, "مرحبا"))
			log_error.assert_called_once()
			self.assertNotIn(KEY, str(log_error.call_args))

	# ---------- Telegram ----------
	def use_telegram(self):
		frappe.conf.pop("imed_whatsapp_recipients", None)
		frappe.conf.imed_telegram_bot_token = TOKEN
		frappe.conf.imed_telegram_chats = {OWNER_USER: CHAT}

	def test_telegram_queues_only_listed_users_and_needs_the_token(self):
		self.use_telegram()
		with patch.object(frappe, "enqueue") as enqueue:
			sent = notification_service.notify(
				"owner_daily_summary", [OWNER_USER, SARA], {"subject": "s", "message": "سطر ١\nسطر ٢"}
			)
		self.assertEqual(sent, {"telegram": [OWNER_USER], "whatsapp": []})
		enqueue.assert_called_once()
		self.assertEqual(enqueue.call_args.args, ("imed_erp.notification_service.send_telegram",))
		self.assertEqual(enqueue.call_args.kwargs["text"], "سطر ١\nسطر ٢")
		self.assertNotIn(TOKEN, str(enqueue.call_args))

		frappe.conf.pop("imed_telegram_bot_token")
		with patch.object(frappe, "enqueue") as enqueue:
			sent = notification_service.notify("owner_daily_summary", [OWNER_USER], {"subject": "s", "message": "m"})
		self.assertEqual(sent, {"telegram": [], "whatsapp": []})
		enqueue.assert_not_called()

	def test_telegram_send_posts_the_text_to_the_users_chat(self):
		self.use_telegram()
		answer = MagicMock(status_code=200, json=lambda: {"ok": True, "result": {"message_id": 1}})
		with patch.object(requests, "post", return_value=answer) as post:
			self.assertTrue(notification_service.send_telegram(OWNER_USER, "مرحبا"))
		self.assertEqual(post.call_args.args, (f"https://api.telegram.org/bot{TOKEN}/sendMessage",))
		self.assertEqual(post.call_args.kwargs["json"], {"chat_id": CHAT, "text": "مرحبا"})
		self.assertFalse(notification_service.send_telegram(SARA, "مرحبا"))  # not listed

	def test_telegram_failure_is_logged_without_the_token_and_not_raised(self):
		self.use_telegram()
		failures = (
			{"return_value": MagicMock(status_code=403, json=lambda: {"ok": False, "description": f"blocked {TOKEN}"})},
			{"return_value": MagicMock(status_code=502, json=MagicMock(side_effect=ValueError("not json")))},
			{"side_effect": requests.ConnectionError(f"https://api.telegram.org/bot{TOKEN}/sendMessage")},
		)
		for failure in failures:
			with patch.object(requests, "post", **failure), patch.object(frappe, "log_error") as log_error:
				self.assertFalse(notification_service.send_telegram(OWNER_USER, "مرحبا"))
			log_error.assert_called_once()
			self.assertNotIn(TOKEN, str(log_error.call_args))

	def test_telegram_chats_lists_who_pressed_start(self):
		self.use_telegram()
		updates = [
			{"message": {"chat": {"id": 987654321, "first_name": "Mohamed", "last_name": "M", "username": "mm"}}},
			{"message": {"chat": {"id": 987654321, "first_name": "Mohamed", "last_name": "M", "username": "mm"}}},
			{"my_chat_member": {"chat": {"id": -100, "title": "IMED"}}},
		]
		answer = MagicMock(status_code=200, json=lambda: {"ok": True, "result": updates})
		with patch.object(requests, "post", return_value=answer):
			chats = notification_service.telegram_chats()
		self.assertEqual(
			chats,
			[
				{"chat_id": 987654321, "name": "Mohamed M", "username": "mm"},
				{"chat_id": -100, "name": "IMED", "username": None},
			],
		)

	# ---------- stock requests ----------
	def test_requesting_approval_tells_the_owner_what_was_asked_for(self):
		request = frappe.get_doc(
			{
				"doctype": "Material Request",
				"material_request_type": "Material Transfer",
				"company": COMPANY,
				"transaction_date": nowdate(),
				"schedule_date": add_days(nowdate(), 1),
				"set_from_warehouse": MAWASAH_STORE,
				"set_warehouse": AZARITA_STORE,
				"items": [{"schedule_date": add_days(nowdate(), 1), "item_code": PAPER, "qty": 2, "uom": CARTON}],
			}
		)
		as_user(SARA, request.insert)
		with patch.object(owner_alerts, "owners", return_value=[OWNER_USER]), patch.object(frappe, "enqueue") as enqueue:
			as_user(SARA, material_issue.request_approval, request.name)
		texts = [c.kwargs["text"] for c in enqueue.call_args_list if c.kwargs.get("user") == OWNER_USER]
		self.assertEqual(len(texts), 1)
		self.assertIn(owner_alerts.short(AZARITA_STORE), texts[0])
		self.assertNotIn(" - MMG", texts[0])
		self.assertIn(request.name, texts[0])
		self.assertIn(f"× 2 {CARTON}", texts[0])

	# ---------- the daily summary ----------
	def test_daily_summary_totals_then_one_line_per_business(self):
		revenue = {"استوديو X - MMG": 3000.0, "مكتبة الأزاريطة - MMG": 9500.5}
		bookings = Counter({"استوديو X - MMG": 4, "قاعات Imed - MMG": 3})
		with (
			patch.object(owner_alerts, "revenue_by_business", return_value=revenue),
			patch.object(owner_alerts, "bookings_by_business", return_value=bookings),
		):
			lines = owner_alerts.daily_summary().split("\n")
		self.assertIn("12,500.50", lines[1])
		self.assertIn("7", lines[2])
		self.assertEqual(lines[3], "")
		# Highest revenue first; the company's abbreviation is left out; bookings only where there are some.
		self.assertTrue(lines[4].startswith("مكتبة الأزاريطة: 9,500.50"))
		self.assertNotIn("·", lines[4])
		self.assertTrue(lines[5].startswith("استوديو X: 3,000.00 · "))
		self.assertIn("4", lines[5])
		self.assertTrue(lines[6].startswith("قاعات Imed: 0.00 · "))
		self.assertEqual(len(lines), 7)

	def test_a_day_with_nothing_still_makes_a_summary_from_the_real_figures(self):
		lines = owner_alerts.daily_summary(add_days(nowdate(), 3650)).split("\n")
		self.assertEqual(len(lines), 3)
		self.assertIn("0.00", lines[1])

	def test_send_daily_summary_goes_to_the_owners_in_their_language(self):
		frappe.get_doc(
			{"doctype": "User", "email": OWNER_USER, "first_name": "Owner Alerts", "language": "ar", "send_welcome_email": 0}
		).insert()
		before = frappe.local.lang
		with patch.object(owner_alerts, "owners", return_value=[OWNER_USER]), patch.object(frappe, "enqueue") as enqueue:
			owner_alerts.send_daily_summary()
		enqueue.assert_called_once()
		self.assertEqual(enqueue.call_args.kwargs["user"], OWNER_USER)
		self.assertTrue(enqueue.call_args.kwargs["text"].split("\n")[1].startswith("الإيراد: "))
		self.assertEqual(frappe.local.lang, before)
