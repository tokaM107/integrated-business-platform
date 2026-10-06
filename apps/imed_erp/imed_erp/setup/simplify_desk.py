# Declutter the desk for Mohamed Mamdouh group: hide the standard ERPNext workspaces (modules) the
# group does not use, so the owner and staff see only the areas that matter instead of ERPNext's full
# 20-module menu. Part of the screen design standard (docs/SCREEN_DESIGN_STANDARD.md).
#
# Run from bench console:
#   exec(open("/home/frappe/frappe-bench/apps/imed_erp/imed_erp/setup/simplify_desk.py").read(), {"frappe": frappe})
#
# UI only: this changes nothing but workspace *visibility*. No data, no doctype, no permission is
# touched; every screen stays reachable by search or direct URL. Idempotent — re-running changes
# nothing. Fully reversible: set RESTORE = True below (or unhide from Edit > Workspaces) to show them
# again.

import frappe

# Standard workspaces to HIDE. These are ERPNext verticals MMG does not run (a lecture-hall / library /
# photo-studio group): no factory, no fixed-asset register, no quality system, no projects desk, no
# help desk, and CRM is not in use yet (the "CRM Staff" role exists but has no user). "Welcome
# Workspace" and "Build" are generic Frappe intro/developer pages. Everything NOT listed here stays
# visible (Owner Dashboard, Invoicing, Financial Reports, Selling, Stock, Buying, Users, Home, ...).
#
# NOTE: this exact list is a business decision — confirm with the owner before treating it as final
# (see docs/SCREEN_DESIGN_STANDARD.md §13, "Needs Business Confirmation").
HIDE = [
    "Assets",
    "Manufacturing",
    "Subcontracting",
    "Quality",
    "Projects",
    "Support",
    "CRM",
    "Welcome Workspace",
    "Build",
]

# Flip to True and re-run to bring every workspace above back.
RESTORE = False


def run():
    target = 0 if RESTORE else 1
    changed = 0
    for name in HIDE:
        if not frappe.db.exists("Workspace", name):
            print(f"skip   Workspace {name} not found")
            continue
        current = frappe.db.get_value("Workspace", name, "is_hidden") or 0
        if current == target:
            print(f"exists Workspace {name}: is_hidden = {target}")
            continue
        frappe.db.set_value("Workspace", name, "is_hidden", target)
        changed += 1
        print(f"set    Workspace {name}: is_hidden {current} -> {target}")

    frappe.db.commit()
    frappe.clear_cache()
    action = "shown" if RESTORE else "hidden"
    print(f"DONE   {changed} workspace(s) {action}. Users reload the page (Ctrl+Shift+R) to see it.")


run()
