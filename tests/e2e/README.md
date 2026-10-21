# Browser tests

Real browser sessions (Playwright, Chromium) as the owner, the accountant, the library, studio, halls and app
managers: logins, pages each may open, server calls each may not make, branch isolation, money operations refused,
Arabic and right-to-left, phone width, and the main workflows through the forms.

They create records, so they run on a **throwaway copy** of the site, never on `frontend`:

```bash
# 1. A copy of the site, from a backup (docs/production-hardening.md, restore).
docker exec frappe_docker-backend-1 bench new-site restore-test --mariadb-user-host-login-scope='%' --db-root-password <root> --admin-password <any>
docker exec frappe_docker-backend-1 bench --site restore-test restore <set>-database.sql.gz --with-public-files <set>-files.tar --with-private-files <set>-private-files.tar --db-root-password <root>
docker exec frappe_docker-backend-1 bench --site restore-test migrate

# 2. A password for the test users, on the copy only.
export IMED_E2E_PASSWORD="E2e-$(openssl rand -hex 8)"
for u in owner accountant raghad sara gilan nour menna hr; do
  docker exec frappe_docker-backend-1 bench --site restore-test set-password "$u@imed.local" "$IMED_E2E_PASSWORD"
done

# 3. The copy reachable from the browser, then the tests.
scripts/e2e_forward.sh
cd tests/e2e && npm install && npx playwright install chromium
node roles.js && node screens.js && node workflows.js && node close.js
```

Screenshots go to `tests/e2e/shots/`. `workflows.js` makes new records on every run (an expense, a transfer, a
booking, a subscription); its scrap step needs an obsolete edition with copies left. `demo_screens.js` (with `IMED_E2E_SITE=demo`) opens the demo site's cash screens and checks their sample
records, read-only. `close.js` reopens today's submitted close of
Azarita's cash box (as the accountant, after checking that Sara cannot), closes the day again 15 short, writes the
shortage off and reviews the week; it needs one submitted close of that box today, and can run again on it.
