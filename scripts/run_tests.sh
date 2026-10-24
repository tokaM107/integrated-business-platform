#!/usr/bin/env bash
# Run the app's tests the safe way: the test-record leak guard first, and nothing else unless it passes.
# A missing IGNORE_TEST_RECORD_DEPENDENCIES entry would otherwise let ERPNext commit thousands of _Test records
# to the site (docs/known-issues.md). Take a backup and copy it out of the container before a run after a schema
# change.
#
#   scripts/run_tests.sh --app imed_erp
#   scripts/run_tests.sh --module imed_erp.imederp.test_doctor_statement
#   scripts/run_tests.sh --doctype "Book Edition"

set -uo pipefail
CONTAINER="${CONTAINER:-frappe_docker-backend-1}"
SITE="${SITE:-frontend}"

guard=$(docker exec "$CONTAINER" bench --site "$SITE" run-tests --module imed_erp.imederp.test_test_records 2>&1)
if ! printf '%s\n' "$guard" | grep -q "^OK"; then
	echo "GUARD FAILED: not running the tests"
	printf '%s\n' "$guard" | tail -30
	exit 1
fi
docker exec "$CONTAINER" bench --site "$SITE" run-tests "$@" 2>&1
