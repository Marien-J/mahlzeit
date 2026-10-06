#!/usr/bin/env bash
# End-to-end smoke test against the running stack (docker compose up -d).
# Issues a fresh household invite with the admin command, then runs Playwright.
set -euo pipefail
cd "$(dirname "$0")/.."
code="$(docker compose exec -T app mahlzeit invite-household --note e2e | awk -F': ' '/^Code/ {print $2}')"
[ -n "$code" ] || { echo "could not create an invite" >&2; exit 1; }
cd frontend
E2E_INVITE_CODE="$code" npx playwright test "$@"
