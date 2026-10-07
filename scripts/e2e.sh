#!/usr/bin/env bash
# End-to-end tests on a phone viewport against the local stack. For test machines only:
# (re)starts the stack with the Open Food Facts stub (profile "e2e") in place of the real
# service, issues fresh household invites with the admin command, then runs Playwright.
# Images must be built (docker compose build). Extra arguments go to Playwright.
set -euo pipefail
cd "$(dirname "$0")/.."
export OFF_BASE_URL=http://offstub:8080 OFF_SEARCH_URL=http://offstub:8080
docker compose --profile e2e up -d --wait
invite() {
  docker compose exec -T app mahlzeit invite-household --note "e2e $1" | awk -F': ' '/^Code/ {print $2}'
}
smoke="$(invite smoke)"
track="$(invite track)"
list="$(invite list)"
[ -n "$smoke" ] && [ -n "$track" ] && [ -n "$list" ] || { echo "could not create invites" >&2; exit 1; }
cd frontend
E2E_INVITE_CODE="$smoke" E2E_TRACK_INVITE_CODE="$track" E2E_LIST_INVITE_CODE="$list" \
  npx playwright test "$@"
