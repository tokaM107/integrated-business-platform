// Copyright (c) 2026, toka mohamed and contributors
// For license information, please see license.txt

frappe.ui.form.on("Doctor Ledger Entry", {
	setup(frm) {
		// A payout comes out of a cash box or a wallet.
		frm.set_query("treasury", () => ({
			filters: { account_type: ["in", ["Cash", "Bank"]], is_group: 0 },
		}));
	},
});
