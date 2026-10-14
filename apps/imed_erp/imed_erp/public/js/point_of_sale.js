// Copyright (c) 2026, toka mohamed and contributors
// For license information, please see license.txt

/*
 * Point of sale (LIB-01): the library sells books, memos and its services — copying, printing and binding — at
 * ERPNext's own Point of Sale page. This adds, above the item list, one button per service and the three steps
 * of a sale, for someone using the screen for the first time. Attached via hooks.py `page_js`.
 *
 * Only adds elements. A button adds its service exactly as clicking the service's card in the item list does
 * (the selector's own item_selected event), with the price ERPNext's POS reads for that card: the Item Price of
 * the POS Profile's price list. So the price, the revenue account (imederp/library_revenue.py), the paper a print
 * or copy uses (imederp/paper_use.py) and every check stay ERPNext's and the app's. A service the POS Profile does
 * not sell (its item group is not on the profile) or that has no price shows as unavailable, never at a made-up
 * price.
 */

frappe.provide("imed.pos");

// The library services (setup/setup_library.py SERVICES), in the order the counter uses them.
imed.pos.SERVICES = ["COPY-SVC", "PRINT-SVC", "BINDING-SVC"];

imed.pos.add_service_bar = function (selector) {
	if (!selector.$component || selector.$component.find(".imed-pos-services").length) return;

	const $bar = $(`
		<div class="imed-pos-services">
			<ol class="imed-pos-steps">
				<li>${__("Choose the customer")}</li>
				<li>${__("Add books, memos or a service")}</li>
				<li>${__("Check the total, then Checkout and take the payment")}</li>
			</ol>
			<div class="imed-pos-service-buttons"></div>
		</div>
	`);
	selector.$component.find(".filter-section").after($bar);
	const $buttons = $bar.find(".imed-pos-service-buttons");

	imed.pos.SERVICES.forEach((item_code) => {
		const $btn = $(
			`<button type="button" class="btn btn-default imed-pos-service" disabled>
				<span class="imed-pos-service-name">${frappe.utils.escape_html(item_code)}</span>
				<span class="imed-pos-service-price"></span>
			</button>`
		).appendTo($buttons);

		imed.pos.get_service(selector, item_code).then((item) => {
			if (!item) {
				$btn.attr("title", __("Not sold at this point of sale, or it has no price."));
				$btn.find(".imed-pos-service-price").text(__("Not available"));
				return;
			}
			$btn.find(".imed-pos-service-name").text(item.item_name || item_code);
			$btn.find(".imed-pos-service-price").text(
				format_currency(item.price_list_rate, item.currency || frappe.defaults.get_default("currency"))
			);
			$btn.prop("disabled", false).on("click", () => {
				selector.events.item_selected({
					field: "qty",
					value: "+1",
					item: {
						item_code: item.item_code,
						uom: item.uom,
						stock_uom: item.stock_uom,
						rate: item.price_list_rate,
					},
				});
			});
		});
	});
};

/* The service as the POS item list gives it (price, unit), or null when this POS Profile does not sell it. */
imed.pos.get_service = async function (selector, item_code) {
	await selector.item_ready_group;
	if (!selector.price_list) {
		const res = await frappe.db.get_value("POS Profile", selector.pos_profile, "selling_price_list");
		selector.price_list = res.message.selling_price_list;
	}
	const doc = selector.events.get_frm().doc;
	const r = await frappe.call({
		method: "erpnext.selling.page.point_of_sale.point_of_sale.get_items",
		args: {
			start: 0,
			page_length: 20,
			price_list: (doc && doc.selling_price_list) || selector.price_list,
			item_group: selector.parent_item_group,
			search_term: item_code,
			pos_profile: selector.pos_profile,
		},
	});
	const item = ((r.message && r.message.items) || []).find((i) => i.item_code === item_code);
	return item && item.price_list_rate ? item : null;
};

// ERPNext loads the POS classes from its bundle when the page opens; the item selector is built later, once the
// POS opening entry is found. Extend its DOM step so the bar is there however the page was reached.
frappe.require("point-of-sale.bundle.js", () => {
	const proto = erpnext.PointOfSale.ItemSelector.prototype;
	if (proto.__imed_services) return;
	proto.__imed_services = true;
	const prepare_dom = proto.prepare_dom;
	proto.prepare_dom = function () {
		prepare_dom.apply(this, arguments);
		imed.pos.add_service_bar(this);
	};
});
