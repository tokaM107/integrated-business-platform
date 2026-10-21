frappe.listview_settings["Cash Discrepancy"] = {
	get_indicator(doc) {
		const colors = {
			"Pending Investigation": "red",
			"Responsibility Determined": "orange",
			"Recovery Recommended": "purple",
			"Pending Review": "orange",
			"Recovery Approved": "blue",
			"Written Off": "gray",
			Explained: "green",
			Withdrawn: "gray",
		};
		return [__(doc.status), colors[doc.status] || "gray", "status,=," + doc.status];
	},
};
