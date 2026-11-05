# Copyright (c) 2026, toka mohamed and contributors
# For license information, please see license.txt

# Sparkle's database, read (owner, 5 Nov 2026): the halls' booking site keeps its bookings in Supabase (Postgres).
# The ERP logs in as erp_reader, a login that may only read these tables, in a read-only transaction: nothing here
# can change Sparkle.

from datetime import date, time
from decimal import Decimal

import frappe
from frappe import _
from frappe.utils import cint, cstr

TIMEOUT = 15  # seconds to connect


class SparkleError(Exception):
	"""Sparkle could not be read: the run stops and says why; nothing already imported changes."""


def plain(value):
	"""A database value as the sync uses it: money as float, days and times as text."""
	if isinstance(value, Decimal):
		return float(value)
	if isinstance(value, (date, time)):
		return value.isoformat()
	return value


class SparkleClient:
	def __init__(self, settings):
		self.settings = settings
		self.connection = None

	def connect(self):
		import psycopg2

		s = self.settings
		if not (s.db_host and s.db_user):
			raise SparkleError(_("Sparkle Settings has no host or user."))
		try:
			self.connection = psycopg2.connect(
				host=s.db_host,
				port=cint(s.db_port) or 5432,
				dbname=s.db_name or "postgres",
				user=s.db_user,
				password=s.get_password("db_password", raise_exception=False) or "",
				connect_timeout=TIMEOUT,
				sslmode="require",
				options="-c default_transaction_read_only=on",
			)
		except Exception as e:
			raise SparkleError(_("Sparkle did not answer: {0}").format(cstr(e).splitlines()[0] if cstr(e) else e.__class__.__name__))
		return self

	def close(self):
		if self.connection:
			self.connection.close()
			self.connection = None

	def rows(self, sql, params=None):
		from psycopg2.extras import RealDictCursor

		if not self.connection:
			self.connect()
		try:
			with self.connection.cursor(cursor_factory=RealDictCursor) as cursor:
				cursor.execute(sql, params)
				return [{k: plain(v) for k, v in row.items()} for row in cursor.fetchall()]
		except Exception as e:
			raise SparkleError(_("Sparkle could not be read: {0}").format(cstr(e).splitlines()[0] if cstr(e) else e.__class__.__name__))

	def bookings(self, since):
		"""Every booking on or after `since`, with its price (booking_quotes)."""
		return self.rows(
			"""select b.id, b.hall_slug, b.booking_date, b.start_time, b.end_time, b.status, b.type, b.customer_id,
				b.full_name, b.whatsapp, b.notes, b.settlement_note, b.created_at,
				q.final_total, q.calculated_total, q.override_total, q.extras_total
			from public.bookings b left join public.booking_quotes q on q.booking_id = b.id
			where b.booking_date >= %s order by b.created_at, b.id""",
			(since,),
		)

	def resources(self, booking_ids):
		"""The physical halls each booking holds (one for most; both for a combined hall such as 5 + 6)."""
		if not booking_ids:
			return []
		return self.rows(
			"select booking_id, physical_slug, booking_date, start_time, end_time from public.booking_resources where booking_id = any(%s::uuid[]) order by booking_id, physical_slug",
			(list(booking_ids),),
		)

	def customers(self, customer_ids):
		if not customer_ids:
			return []
		return self.rows("select id, full_name, phone_normalized, company from public.customers where id = any(%s::uuid[])", (list(customer_ids),))

	def payments(self, booking_ids):
		"""The bookings' money: each entry as Sparkle recorded it (a payment, its reversal, its undoing...)."""
		if not booking_ids:
			return []
		return self.rows(
			"select id, booking_id, kind, amount, paid_on, method, reference, note, reverses_id, created_at from public.payments where booking_id = any(%s::uuid[]) order by created_at, id",
			(list(booking_ids),),
		)

	def halls(self):
		return self.rows("select slug, is_active, is_combined from public.halls order by slug")
