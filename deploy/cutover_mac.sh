#!/usr/bin/env bash
# Cutover, Mac side (runbook section 14 B, steps 1-2): pause the Mac's scheduler, wait for a running XStudio
# import to end, take the final backup with files, check it, keep an independent copy, and send the set to the
# VPS. Prints the set name for deploy/cutover_vps.sh. Run only on the owner's GO.
#
#   KEEP_DIR=/Volumes/<owner's drive>/imed-cutover deploy/cutover_mac.sh
#   deploy/cutover_mac.sh --check      only shows the state, changes nothing
set -euo pipefail
CONTAINER="${CONTAINER:-frappe_docker-backend-1}"
SITE="${SITE:-frontend}"
VPS="${VPS:-root@72.62.36.46}"
KEY="${KEY:-$HOME/.ssh/hostinger_vps}"
REMOTE_DIR="${REMOTE_DIR:-/root/imed-restore}"
KEEP_DIR="${KEEP_DIR:-$HOME/imed-cutover}"
bench() { docker exec "$CONTAINER" bench --site "$SITE" "$@"; }

echo "Mac site $SITE: $(bench scheduler status | tail -1)"
running=$(bench execute frappe.db.count --args "['Integration Import Log', {'status': 'Running'}]" | tail -1)
echo "XStudio imports running now: ${running:-0}"
if [ "${1:-}" = "--check" ]; then
	echo "check only: nothing changed"; exit 0
fi

echo "1. pausing the Mac's scheduler (the Mac stops syncing XStudio from now on)"
bench disable-scheduler | tail -1
for i in $(seq 1 30); do
	running=$(bench execute frappe.db.count --args "['Integration Import Log', {'status': 'Running'}]" | tail -1)
	[ "${running:-0}" = "0" ] && break
	echo "   an import is still running; waiting (${i})"; sleep 10
done

echo "2. final backup with files"
out=$(bench backup --with-files 2>&1)
prefix=$(printf '%s\n' "$out" | sed -n 's#.*/\([0-9_]*-[^/]*\)-database\.sql\.gz.*#\1#p' | head -1)
[ -n "$prefix" ] || { printf '%s\n' "$out"; echo "no backup made" >&2; exit 1; }
mkdir -p "$KEEP_DIR/$prefix"; chmod 700 "$KEEP_DIR" "$KEEP_DIR/$prefix"
for f in database.sql.gz files.tar private-files.tar site_config_backup.json; do
	docker cp "$CONTAINER:/home/frappe/frappe-bench/sites/$SITE/private/backups/$prefix-$f" "$KEEP_DIR/$prefix/$prefix-$f"
done
chmod 600 "$KEEP_DIR/$prefix"/*
gzip -t "$KEEP_DIR/$prefix/$prefix-database.sql.gz"
tar -tf "$KEEP_DIR/$prefix/$prefix-files.tar" >/dev/null
tar -tf "$KEEP_DIR/$prefix/$prefix-private-files.tar" >/dev/null
python3 -c "import json,sys; d=json.load(open(sys.argv[1])); assert d.get('encryption_key'), 'no encryption key in the set'" "$KEEP_DIR/$prefix/$prefix-site_config_backup.json"
echo "   set $prefix checked; independent copy in $KEEP_DIR/$prefix (keep it)"
bench execute imed_erp.setup.counts.run | tail -1 > "$KEEP_DIR/$prefix/counts-mac.json"

echo "3. sending the set to the VPS"
ssh -i "$KEY" "$VPS" "mkdir -p $REMOTE_DIR && chmod 700 $REMOTE_DIR"
scp -q -i "$KEY" "$KEEP_DIR/$prefix"/$prefix-* "$VPS:$REMOTE_DIR/"
ssh -i "$KEY" "$VPS" "chmod 600 $REMOTE_DIR/$prefix-*; sha256sum $REMOTE_DIR/$prefix-database.sql.gz | cut -c1-16"
shasum -a 256 "$KEEP_DIR/$prefix/$prefix-database.sql.gz" | cut -c1-16
echo "SET=$prefix"
echo "next, on the VPS: SET=$prefix /root/imed-restore/cutover_vps.sh"
