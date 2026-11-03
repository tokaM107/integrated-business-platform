#!/usr/bin/env bash
# Nightly encrypted off-server backup of the IMED ERP, run on the VPS host by root's cron (restic + rclone to the
# company's Google Drive; zero cost). Installed at /usr/local/sbin/imed-offsite-backup.sh.
#
#   imed-offsite-backup.sh              one backup: bench set with files -> staging -> restic -> check -> retention
#   imed-offsite-backup.sh status       the last result (what a monitor or a person reads)
#   imed-offsite-backup.sh verify       non-destructive recovery test: restore the latest snapshot to a temp folder
#                                       and check the archives and the encryption key (no site is touched)
#
# Secrets live in /root/.imed-backup.env (mode 600, outside git): RESTIC_PASSWORD (typed by the owner, kept by the
# owner) and RESTIC_REPOSITORY (rclone:gdrive-imed:imed-erp-backups). The Google token is in rclone's config.
# Each snapshot holds: database dump, public files, private files, site config (with the encryption key and the
# installed apps) and RECOVERY.txt (how to restore). Retention: 30 daily, 12 weekly, 12 monthly.
set -uo pipefail
ENV=/root/.imed-backup.env
STAGE=/var/backups/imed
LOG=/var/log/imed-backup.log
STATUS=$STAGE/LAST_STATUS
SITE=frontend
stamp() { date -u '+%Y-%m-%dT%H:%M:%SZ'; }
say() { echo "$(stamp) $*" | tee -a "$LOG"; }
fail() { say "FAILED: $*"; echo "FAILED $(stamp) $*" > "$STATUS"; exit 1; }
[ -r "$ENV" ] || fail "$ENV missing (RESTIC_PASSWORD, RESTIC_REPOSITORY)"
set -a; . "$ENV"; set +a
[ -n "${RESTIC_PASSWORD:-}" ] && [ -n "${RESTIC_REPOSITORY:-}" ] || fail "RESTIC_PASSWORD or RESTIC_REPOSITORY empty"
B=$(docker ps --filter "name=backend-ctxd8" --format '{{.Names}}' | head -1)
[ -n "$B" ] || fail "backend container not running"

case "${1:-backup}" in
status)
	cat "$STATUS" 2>/dev/null || echo "no backup recorded yet"; tail -3 "$LOG" 2>/dev/null; exit 0 ;;
verify)
	tmp=$(mktemp -d /var/backups/imed/verify.XXXX)
	say "verify: restoring the latest snapshot into $tmp"
	restic restore latest --target "$tmp" >>"$LOG" 2>&1 || fail "restic restore"
	db=$(find "$tmp" -name '*-database.sql.gz' | head -1); [ -n "$db" ] || fail "no database in snapshot"
	gzip -t "$db" || fail "database archive corrupt"
	for t in $(find "$tmp" -name '*.tar'); do tar -tf "$t" >/dev/null || fail "archive $t corrupt"; done
	cfg=$(find "$tmp" -name '*-site_config_backup.json' | head -1)
	python3 -c "import json,sys; d=json.load(open(sys.argv[1])); assert d.get('encryption_key') and d.get('installed_apps'), 'key or apps missing'" "$cfg" || fail "site config incomplete"
	rows=$(gzip -dc "$db" | grep -c "^INSERT INTO \`tabBooking\`" || true)
	say "verify OK: $(basename "$db"), $(du -sh "$tmp" | cut -f1), key present, Booking inserts $rows"
	rm -rf "$tmp"; echo "VERIFY OK $(stamp) $(basename "$db")" >> "$STATUS"; exit 0 ;;
backup) ;;
*) echo "usage: $0 [backup|status|verify]"; exit 2 ;;
esac

mkdir -p "$STAGE"; chmod 700 "$STAGE"
say "backup starting ($B)"
out=$(docker exec "$B" bench --site "$SITE" backup --with-files 2>&1) || fail "bench backup: $out"
prefix=$(printf '%s\n' "$out" | sed -n 's#.*/\([0-9_]*-[^/]*\)-database\.sql\.gz.*#\1#p' | head -1)
[ -n "$prefix" ] || fail "bench reported no database file"
set=$STAGE/$prefix; mkdir -p "$set"; chmod 700 "$set"
for f in database.sql.gz files.tar private-files.tar site_config_backup.json; do
	docker cp "$B:/home/frappe/frappe-bench/sites/$SITE/private/backups/$prefix-$f" "$set/$prefix-$f" || fail "copy $f"
done
chmod 600 "$set"/*
gzip -t "$set/$prefix-database.sql.gz" || fail "database archive"
tar -tf "$set/$prefix-files.tar" >/dev/null || fail "files archive"
tar -tf "$set/$prefix-private-files.tar" >/dev/null || fail "private files archive"
python3 -c "import json,sys; d=json.load(open(sys.argv[1])); assert d.get('encryption_key'), 'no key'" "$set/$prefix-site_config_backup.json" || fail "encryption key missing from the set"
cat > "$set/RECOVERY.txt" <<REC
IMED ERP backup set $prefix (taken $(stamp) on the Hostinger VPS, site $SITE).
Restore: deploy/restore_site.sh from the repository's production branch, e.g.
  BACKEND=<backend container> SET=$prefix BACKUP_DIR=<folder with these files> DB_ROOT_PASSWORD=<stack password> HOST_NAME=https://erpmohamedmamdouh.tech deploy/restore_site.sh
The site_config_backup.json carries the encryption key: without it the stored passwords (XStudio) cannot be read.
The restic password is the owner's; the Google Drive account is academyimed11@gmail.com (rclone remote gdrive-imed).
REC
say "set $prefix made and checked ($(du -sh "$set" | cut -f1))"
# Google Drive answers an occasional transient 500: each step is tried up to three times, a minute apart.
try3() { for i in 1 2 3; do "$@" >>"$LOG" 2>&1 && return 0; say "attempt $i failed: $*"; sleep 60; done; return 1; }
restic snapshots --latest 1 >/dev/null 2>&1 || try3 restic init || fail "restic init"
try3 restic backup --tag imed-erp "$set" || fail "restic backup (upload)"
restic check >>"$LOG" 2>&1 || fail "restic check"
restic forget --tag imed-erp --keep-daily 30 --keep-weekly 12 --keep-monthly 12 --prune >>"$LOG" 2>&1 || say "warning: retention/prune failed (backup itself is stored)"
snap=$(restic snapshots --latest 1 --json 2>/dev/null | python3 -c 'import sys,json; print(json.load(sys.stdin)[-1]["short_id"])' 2>/dev/null)
find "$STAGE" -mindepth 1 -maxdepth 1 -type d -name '2026*' -mtime +7 -exec rm -rf {} + 2>/dev/null
say "OFFSITE OK $prefix snapshot $snap"
echo "OK $(stamp) $prefix snapshot $snap" > "$STATUS"
