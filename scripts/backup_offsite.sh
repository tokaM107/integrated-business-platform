#!/usr/bin/env bash
# Daily backup of the ERP, kept off the server (SEC-05).
#
#   1. bench backup --with-files: the database, the site config, and the public and private files (receipts).
#   2. The new set is copied out of the container into BACKUP_DIR on the host, in a folder of its own.
#   3. Each archive is checked (gzip -t, tar -t) before the backup counts as made.
#   4. With REMOTE set (an rclone remote, e.g. "gdrive:imed-backups"), the folder is copied there too:
#      that is the off-server copy. Without it the backup stays on this machine only, and the script says so.
#   5. Sets older than KEEP_DAYS are removed from BACKUP_DIR (never from the remote).
#
# bench backup removes its own backups older than about a day inside the container, so the copy in step 2 is
# what keeps the history.
#
# Run every night from cron on the host, e.g.:
#   30 2 * * * BACKUP_DIR=/srv/imed-backups REMOTE=gdrive:imed-backups /path/to/scripts/backup_offsite.sh >> /var/log/imed-backup.log 2>&1
#
# Restore (try it once before go-live, on a test site):
#   docker exec <backend> bench --site <test-site> restore /path/in/container/<set>-database.sql.gz \
#     --with-public-files <set>-files.tar --with-private-files <set>-private-files.tar

set -euo pipefail

CONTAINER="${CONTAINER:-frappe_docker-backend-1}"
SITE="${SITE:-frontend}"
BACKUP_DIR="${BACKUP_DIR:-$HOME/imed-backups}"
KEEP_DAYS="${KEEP_DAYS:-30}"
REMOTE="${REMOTE:-}"
BENCH_BACKUPS="/home/frappe/frappe-bench/sites/${SITE}/private/backups"

stamp() { date '+%Y-%m-%d %H:%M:%S'; }

echo "$(stamp) backup of ${SITE} starting"
output=$(docker exec "$CONTAINER" bench --site "$SITE" backup --with-files 2>&1)
# The set's prefix (e.g. 20261020_170527-frontend) from the database file bench reports.
prefix=$(printf '%s\n' "$output" | sed -n 's#.*/\([0-9_]*-[^/]*\)-database\.sql\.gz.*#\1#p' | head -1)
if [ -z "$prefix" ]; then
	printf '%s\n' "$output"
	echo "$(stamp) FAILED: bench did not report a database backup" >&2
	exit 1
fi

target="${BACKUP_DIR}/${prefix}"
# The site config in the set holds the database password: the folder is the owner's only.
mkdir -p "$target"
chmod 700 "$BACKUP_DIR" "$target"
for file in $(docker exec "$CONTAINER" bash -c "ls ${BENCH_BACKUPS} | grep '^${prefix}'"); do
	docker cp "${CONTAINER}:${BENCH_BACKUPS}/${file}" "${target}/${file}"
done

# A backup that cannot be read is no backup.
gzip -t "${target}/${prefix}-database.sql.gz"
for archive in "${target}"/*.tar; do
	[ -e "$archive" ] && tar -tf "$archive" > /dev/null
done
chmod 600 "$target"/*
echo "$(stamp) copied and checked: ${target} ($(du -sh "$target" | cut -f1))"

if [ -n "$REMOTE" ]; then
	rclone copy "$target" "${REMOTE}/${prefix}"
	echo "$(stamp) copied off the server to ${REMOTE}/${prefix}"
else
	echo "$(stamp) WARNING: REMOTE is not set; this backup is on this machine only" >&2
fi

find "$BACKUP_DIR" -mindepth 1 -maxdepth 1 -type d -mtime +"$KEEP_DAYS" -exec rm -rf {} +
echo "$(stamp) done"
