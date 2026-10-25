#!/usr/bin/env bash
# Prepare a STAGING XStudio (its API, not its database) for the ERP sync, using only XStudio's existing endpoints:
#   1. log in as the seed super admin (seed.sql: admin@xstudio.local / ChangeMe!2026) and change that password;
#   2. create the `accountant` staff login the ERP sync uses (bookings.read + packages.read).
# Nothing is printed that is secret. Refuses to run against xstudioeg.com.
#
#   XSTUDIO_URL=http://localhost:4000 ADMIN_NEW_PASSWORD=... SYNC_PHONE=+2010... SYNC_PASSWORD=... scripts/xstudio_staging.sh
#   (optional) ADMIN_LOGIN=admin@xstudio.local ADMIN_PASSWORD='ChangeMe!2026'

set -euo pipefail
URL="${XSTUDIO_URL:?set XSTUDIO_URL, the staging server, e.g. http://localhost:4000}"
case "$URL" in *xstudioeg.com*) echo "refusing: that is the production site"; exit 1;; esac
ADMIN_LOGIN="${ADMIN_LOGIN:-admin@xstudio.local}"
ADMIN_PASSWORD="${ADMIN_PASSWORD:-ChangeMe!2026}"
: "${ADMIN_NEW_PASSWORD:?set ADMIN_NEW_PASSWORD, 8 chars or more}"
: "${SYNC_PHONE:?set SYNC_PHONE, the accountant login phone, e.g. +201000000002}"
: "${SYNC_PASSWORD:?set SYNC_PASSWORD, 8 chars or more}"

json() { python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get(sys.argv[1], ""))' "$1"; }

curl -fsS "$URL/api/health" >/dev/null || { echo "XStudio is not answering at $URL"; exit 1; }

if [[ "$ADMIN_LOGIN" == *@* ]]; then body="{\"email\":\"$ADMIN_LOGIN\",\"password\":\"$ADMIN_PASSWORD\"}"; else body="{\"phone\":\"$ADMIN_LOGIN\",\"password\":\"$ADMIN_PASSWORD\"}"; fi
TOKEN=$(curl -fsS -H 'Content-Type: application/json' -d "$body" "$URL/api/auth/login" | json token)
[[ -n "$TOKEN" ]] || { echo "admin login failed"; exit 1; }

# 1. the seed password must not stay
curl -fsS -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d "{\"oldPassword\":\"$ADMIN_PASSWORD\",\"newPassword\":\"$ADMIN_NEW_PASSWORD\"}" "$URL/api/me/password" >/dev/null
echo "admin password changed"

# 2. the sync's own login (role accountant: bookings.read + packages.read; no bookings.write)
out=$(curl -sS -w '\n%{http_code}' -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d "{\"name\":\"ERP Sync\",\"phone\":\"$SYNC_PHONE\",\"password\":\"$SYNC_PASSWORD\",\"role\":\"accountant\"}" "$URL/api/admin/users")
code=$(printf '%s' "$out" | tail -1)
case "$code" in
  201) echo "sync login created (accountant)";;
  409) echo "sync login already exists";;
  *) echo "creating the sync login failed ($code)"; exit 1;;
esac
echo "done: enter $URL, the sync phone and its password on XStudio Settings."
