#!/usr/bin/env bash
# Prove the off-server backup can be recovered: fetch the latest restic snapshot, restore it into a SECOND site in
# the same stack (never over the live one), compare the record counts with the live site, then drop the check
# site. Run on the host (where docker is), monthly and before every version:
#
#   BACKEND=<backend container> DB_ROOT_PASSWORD=<the stack's> deploy/verify_backup.sh
#
# The restic variables are read from the backend container's own environment (Coolify's), so nothing is typed.
set -euo pipefail
BACKEND="${BACKEND:?backend container}"
DB_ROOT_PASSWORD="${DB_ROOT_PASSWORD:?the MariaDB root password of the stack}"
LIVE="${SITE:-frontend}"
CHECK="${CHECK_SITE:-restore-check}"
work=/home/frappe/frappe-bench/sites/verify-in
here=$(cd "$(dirname "$0")" && pwd)

# The restic variables: the container's own (Coolify's environment), or passed from this shell for a drill.
pass=()
for v in RESTIC_REPOSITORY RESTIC_PASSWORD AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY; do
	[ -n "${!v:-}" ] && pass+=(-e "$v=${!v}")
done
echo "fetching the latest snapshot into the container"
docker exec "$BACKEND" rm -rf "$work"
docker exec "${pass[@]}" "$BACKEND" restic restore latest --target "$work" | tail -1
dbfile=$(docker exec "$BACKEND" find "$work" -name '*-database.sql.gz' | head -1)
[ -n "$dbfile" ] || { echo "no database file in the snapshot" >&2; exit 1; }
prefix=$(basename "$dbfile" -database.sql.gz)
setdir=$(dirname "$dbfile")
echo "snapshot holds set $prefix"

tmp=$(mktemp -d)
for f in database.sql.gz files.tar private-files.tar site_config_backup.json; do
	docker cp "$BACKEND:$setdir/$prefix-$f" "$tmp/$prefix-$f"
done
if docker exec "$BACKEND" test -d "/home/frappe/frappe-bench/sites/$CHECK"; then FORCE=1; else FORCE=0; fi
FORCE=$FORCE BACKEND="$BACKEND" SET="$prefix" BACKUP_DIR="$tmp" DB_ROOT_PASSWORD="$DB_ROOT_PASSWORD" SITE="$CHECK" "$here/restore_site.sh" | tail -12
rm -rf "$tmp"
docker exec "$BACKEND" rm -rf "$work"

echo "comparing $CHECK with $LIVE (imed_erp.setup.counts.run)"
live=$(docker exec "$BACKEND" bench --site "$LIVE" execute imed_erp.setup.counts.run | tail -1)
snap=$(docker exec "$BACKEND" bench --site "$CHECK" execute imed_erp.setup.counts.run | tail -1)
same=$(python3 "$here/compare_counts.py" "$live" "$snap")
echo "dropping $CHECK"
docker exec "$BACKEND" bench drop-site "$CHECK" --db-root-password "$DB_ROOT_PASSWORD" --force --no-backup 2>&1 | tail -1
[ "$same" = "1" ] && echo "RECOVERY OK: snapshot $prefix restores and matches the live counts (differences are expected only for records made after the backup)" || echo "RECOVERY: counts differ (fine if the live site changed since the backup; otherwise investigate)"
