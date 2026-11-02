# The roles the app's rules name, defined once (audit of 2 Nov 2026: "Super Admin" was written in three modules and
# ("Accounts Manager", "System Manager") in five). A leaf module: it imports nothing of the app.
#
# Who holds what (setup/setup_users.py): the owner holds Super Admin, System Manager and Accounts Manager; the
# accountant holds Accountant and Accounts Manager. Each module keeps its own set of roles: the sets are not merged
# here, because merging them would change who may do what.

OWNER = "Super Admin"
ACCOUNTANT = "Accountant"
ACCOUNTS_MANAGER = "Accounts Manager"
SYSTEM_MANAGER = "System Manager"

# Who acts on the books' cash documents (reopen a close, decide a discrepancy, cancel a hand-over, price a package).
ACCOUNTS_ROLES = (ACCOUNTS_MANAGER, SYSTEM_MANAGER)
# Who reads the company's figures as a whole (owner_figures.check_reader).
FIGURE_READERS = (OWNER, SYSTEM_MANAGER, ACCOUNTS_MANAGER, ACCOUNTANT)
