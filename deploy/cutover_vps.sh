#!/usr/bin/env bash
# Cutover, VPS side (runbook section 14 B, steps 3-5 and 8): restore the final set over the validated copy, disable
# the twelve verified test users, drop the sessions copied from the Mac, run the XStudio dry run, and stop with
# the site still in maintenance mode and the scheduler still disabled. The owner's passwords (step 6), the login
# rules (7), lifting maintenance mode (9), the switch (10) and enabling the scheduler (11) stay manual and
# approved one by one. Run as root on the VPS, from /root/imed-restore, only on the owner's GO.
#
#   SET=<prefix> /root/imed-restore/cutover_vps.sh
set -euo pipefail
SET="${SET:?the backup set prefix}"
HERE=$(cd "$(dirname "$0")" && pwd)
HOST_NAME="${HOST_NAME:-https://erpmohamedmamdouh.tech}"
B=$(docker ps --filter "name=backend-ctxd8" --format '{{.Names}}' | head -1)
[ -n "$B" ] || { echo "no backend container" >&2; exit 1; }
export DB_ROOT_PASSWORD="$(docker exec "$B" printenv DB_ROOT_PASSWORD)"
[ -n "$DB_ROOT_PASSWORD" ] || { echo "no DB_ROOT_PASSWORD in the backend's environment" >&2; exit 1; }
bench() { docker exec "$B" bench --site frontend "$@"; }

echo "3. restoring $SET over the validated copy (maintenance mode stays on, scheduler stays off)"
FORCE=1 BACKEND="$B" SET="$SET" BACKUP_DIR="$HERE" HOST_NAME="$HOST_NAME" "$HERE/restore_site.sh" | tail -8
bench set-maintenance-mode on | tail -1

echo "4. the twelve verified test users"
bench execute imed_erp.setup.review_test_users.run | tail -1 | python3 -c "
import sys, json
d = json.load(sys.stdin)
bad = [u for u, v in d.items() if isinstance(v, dict) and (v['last_login'] or v['owner_or_modifier_of'] or v['open_sessions'])]
print('   users reviewed:', len(d), '| unexpected activity on:', bad or 'none')
sys.exit(1 if bad else 0)"
bench execute imed_erp.setup.review_test_users.disable_users --kwargs "{'users': ['marcus@abc.com','mathias@abc.com','thalia@abc.com','test@example.com','test1@example.com','test2@example.com','test3@example.com','test4@example.com',\"test'5@example.com\",'testdelete@example.com','testpassword@example.com','testperm@example.com']}" | tail -1

echo "5. dropping the sessions copied from the Mac"
bench execute frappe.db.sql --args '["delete from tabSessions"]' >/dev/null
bench execute frappe.db.sql --args '["select count(*) from tabSessions"]' | tail -1
bench clear-cache >/dev/null

echo "8. XStudio dry run from the VPS (reads only)"
bench execute imed_erp.imederp.xstudio.sync.dry_run | tail -1 | python3 -c "
import sys, json
d = json.loads(sys.stdin.read().strip())
print('  ', d.get('status'), d.get('counts'))
print('   would fail:', [(r['external_id'][:30], r['reason'][:60]) for r in d.get('would_fail', [])])"

echo "state: $(bench scheduler status | tail -1); maintenance_mode: $(docker exec "$B" grep -o '"maintenance_mode": [0-9]' sites/frontend/site_config.json)"
bench execute imed_erp.setup.counts.run | tail -1
echo "next (manual, each on approval): 6 passwords, 7 login rules, 9 set-maintenance-mode off, 10 switch, 11 enable-scheduler"
