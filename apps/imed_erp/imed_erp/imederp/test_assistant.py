# Copyright (c) 2026, toka mohamed and Contributors
# See license.txt

# The assistant's endpoint before a paid model is connected (SEC-11): a voice message too long is refused before it
# is decoded, and the endpoint is rate limited.
#
# Run:
#   bench --site frontend run-tests --module imed_erp.imederp.test_assistant

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from imed_erp.assistant import api


class IntegrationTestAssistant(IntegrationTestCase):
	def test_sec11_a_voice_message_too_long_is_refused_before_decoding(self):
		too_long = "A" * ((api.MAX_AUDIO_BYTES + 2) // 3 * 4 + 4)
		with patch("base64.b64decode") as decode:
			self.assertRaisesRegex(frappe.ValidationError, "too long", api.decode_audio, too_long, "audio/webm")
		decode.assert_not_called()

	def test_sec11_the_endpoint_is_rate_limited(self):
		# Inside a web request from one address: the first MESSAGES_PER_MINUTE calls go through (stopped here
		# right after the limit, before any model is asked), the next is refused.
		class Reached(Exception):
			pass

		request = frappe._dict(method="POST")
		with patch.object(frappe.local, "request", request, create=True), patch.object(
			frappe.local, "request_ip", "203.0.113.7", create=True
		), patch.object(frappe.local, "form_dict", frappe._dict(cmd="imed_erp.assistant.api.send_message")), patch.object(
			api, "check_access", side_effect=Reached
		):
			frappe.cache.delete_keys("rl:imed_erp.assistant.api.send_message")
			try:
				for _ in range(api.MESSAGES_PER_MINUTE):
					self.assertRaises(Reached, api.send_message, messages="[]")
				self.assertRaises(frappe.RateLimitExceededError, api.send_message, messages="[]")
			finally:
				frappe.cache.delete_keys("rl:imed_erp.assistant.api.send_message")
