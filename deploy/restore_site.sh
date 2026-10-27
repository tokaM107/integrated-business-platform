#!/usr/bin/env bash
# Restore the IMED ERP site from a backup set into a running stack (the Coolify stack on the server, or a local
# rehearsal of it). Runs on the host; everything happens inside the backend container. Nothing is deleted: a site
# that already exists in the target stack stops the script unless FORCE=1.
#
#   BACKEND=<backend container> SET=<prefix like 20261027_145315-frontend> BACKUP_DIR=<folder with the 4 files> \
#   DB_ROOT_PASSWORD=<the stack's> HOST_NAME=https://erp.example.com deploy/restore_site.sh
#
# The four files of a bench backup set: <SET>-database.sql.gz, <SET>-files.tar, <SET>-private-files.tar and
# <SET>-site_config_backup.json. The last one carries the encryption key that unlocks the stored passwords
# (XStudio Settings' password): without it the restored site cannot read them (verified 27 Oct 2026 on a local
# restore). The scheduler stays disabled on the restored site: enabling it is a separate, approved step
# (docs/PRODUCTION_DEPLOYMENT_COOLIFY.md, section 5).
set -euo pipefail

BACKEND="${BACKEND:?the backend container name}"
SET="${SET:?the backup set prefix}"
BACKUP_DIR="${BACKUP_DIR:?folder holding the backup set}"
DB_ROOT_PASSWORD="${DB_ROOT_PASSWORD:?the MariaDB root password of the stack}"
SITE="${SITE:-frontend}"
HOST_NAME="${HOST_NAME:-}"
ADMIN_PASSWORD="${ADMIN_PASSWORD:-}"   # only used to create the site shell; the restore brings the real accounts
FORCE="${FORCE:-0}"

bench() { docker exec -e DB_ROOT_PASSWORD="$DB_ROOT_PASSWORD" "$BACKEND" bench "$@"; }
inside=/home/frappe/frappe-bench/sites/restore-in

for f in database.sql.gz files.tar private-files.tar site_config_backup.json; do
	[ -f "$BACKUP_DIR/$SET-$f" ] || { echo "missing $BACKUP_DIR/$SET-$f" >&2; exit 1; }
done
gzip -t "$BACKUP_DIR/$SET-database.sql.gz"
tar -tf "$BACKUP_DIR/$SET-files.tar" >/dev/null
tar -tf "$BACKUP_DIR/$SET-private-files.tar" >/dev/null
echo "backup set $SET checked"

if docker exec "$BACKEND" test -d "/home/frappe/frappe-bench/sites/$SITE"; then
	if [ "$FORCE" != "1" ]; then
		echo "site $SITE already exists in $BACKEND: set FORCE=1 to restore over it (it will be replaced)" >&2
		exit 1
	fi
else
	echo "creating the empty site $SITE"
	bench new-site "$SITE" --mariadb-user-host-login-scope='%' --db-root-username=root --db-root-password="$DB_ROOT_PASSWORD" \
		--admin-password="${ADMIN_PASSWORD:-$(openssl rand -hex 16)}" --install-app erpnext --set-default >/dev/null
fi

docker exec "$BACKEND" mkdir -p "$inside"
for f in database.sql.gz files.tar private-files.tar site_config_backup.json; do
	docker cp "$BACKUP_DIR/$SET-$f" "$BACKEND:$inside/$SET-$f"
done
# docker cp keeps the host's owner and mode; the bench runs as the frappe user.
docker exec -u root "$BACKEND" chown -R frappe:frappe "$inside"
docker exec -u root "$BACKEND" chmod -R u+r "$inside"

echo "restoring the database and the files"
bench --site "$SITE" restore "$inside/$SET-database.sql.gz" \
	--with-public-files "$inside/$SET-files.tar" --with-private-files "$inside/$SET-private-files.tar" \
	--db-root-password="$DB_ROOT_PASSWORD" --force | tail -2

echo "carrying over the encryption key (never printed)"
key=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['encryption_key'])" "$BACKUP_DIR/$SET-site_config_backup.json")
docker exec "$BACKEND" bench --site "$SITE" set-config encryption_key "$key" >/dev/null
unset key

echo "production settings on the site"
bench --site "$SITE" set-config developer_mode 0 >/dev/null
bench --site "$SITE" set-config allow_tests 0 >/dev/null
bench --site "$SITE" set-config maintenance_mode 0 >/dev/null
[ -n "$HOST_NAME" ] && bench --site "$SITE" set-config host_name "$HOST_NAME" >/dev/null
bench --site "$SITE" disable-scheduler | tail -1

echo "migrating (the code of the image against the restored database)"
bench --site "$SITE" migrate | tail -2
bench --site "$SITE" clear-cache >/dev/null
docker exec "$BACKEND" rm -rf "$inside"

echo "checks"
bench --site "$SITE" execute frappe.utils.password.get_decrypted_password --args "['XStudio Settings','XStudio Settings','password']" >/dev/null \
	&& echo "  stored passwords decrypt: yes" || echo "  stored passwords decrypt: NO (encryption key missing)"
bench --site "$SITE" execute imed_erp.setup.counts.run | tail -1
bench --site "$SITE" scheduler status
echo "done: the site is restored, the scheduler is disabled"
