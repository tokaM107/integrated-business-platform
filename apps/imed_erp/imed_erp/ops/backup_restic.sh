#!/usr/bin/env bash
# Nightly backup of the ERP off the server with restic, run INSIDE the backend container (Coolify → the application
# → Scheduled Tasks, container `backend`, e.g. "30 2 * * *"):
#
#   bash /home/frappe/frappe-bench/apps/imed_erp/imed_erp/ops/backup_restic.sh   (the script is inside the image, with the app)
#
# Needs in the container's environment (Coolify, marked secret): RESTIC_REPOSITORY (s3:https://<endpoint>/<bucket>/imed-erp),
# RESTIC_PASSWORD, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY. SITE defaults to frontend.
#
# What it does, in order, and stops at the first failure (a backup that was not checked is not a backup):
#   1. bench backup --with-files: the database, the public and private files, the site config (with the encryption key).
#   2. gzip -t / tar -t on the new set.
#   3. restic backup of the set's four files (the repository is initialised on first use).
#   4. restic check of the repository's structure.
#   5. keeps 30 daily, 12 weekly, 12 monthly snapshots; prunes the rest.
#   6. prints the snapshot id and the set's prefix: the line to look for in Coolify's task log.
# Recovery is verified separately by deploy/verify_backup.sh (restore into a second site and compare counts).
set -euo pipefail
SITE="${SITE:-frontend}"
BENCH=/home/frappe/frappe-bench
BACKUPS="$BENCH/sites/$SITE/private/backups"
: "${RESTIC_REPOSITORY:?set RESTIC_REPOSITORY}"
: "${RESTIC_PASSWORD:?set RESTIC_PASSWORD}"

cd "$BENCH"
output=$(bench --site "$SITE" backup --with-files 2>&1)
prefix=$(printf '%s\n' "$output" | sed -n 's#.*/\([0-9_]*-[^/]*\)-database\.sql\.gz.*#\1#p' | head -1)
[ -n "$prefix" ] || { printf '%s\n' "$output"; echo "FAILED: bench made no database backup" >&2; exit 1; }
gzip -t "$BACKUPS/$prefix-database.sql.gz"
tar -tf "$BACKUPS/$prefix-files.tar" >/dev/null
tar -tf "$BACKUPS/$prefix-private-files.tar" >/dev/null
test -s "$BACKUPS/$prefix-site_config_backup.json"
echo "set $prefix made and checked"

restic snapshots --latest 1 >/dev/null 2>&1 || restic init
restic backup --tag imed-erp --tag "$SITE" "$BACKUPS/$prefix-database.sql.gz" "$BACKUPS/$prefix-files.tar" "$BACKUPS/$prefix-private-files.tar" "$BACKUPS/$prefix-site_config_backup.json" 2>&1 | tail -3
restic check 2>&1 | tail -1
restic forget --tag imed-erp --keep-daily 30 --keep-weekly 12 --keep-monthly 12 --prune 2>&1 | tail -1
echo "OFFSITE OK $prefix $(restic snapshots --latest 1 --json | python3 -c 'import sys,json; print(json.load(sys.stdin)[-1]["short_id"])')"
