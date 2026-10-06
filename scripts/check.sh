#!/usr/bin/env bash
# All fast checks a commit must pass: backend lint, format, types, tests; frontend lint, types,
# tests; generated API client up to date. Needs the dev database:
#   docker compose --profile dev up -d devdb
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"

echo "== backend"
cd "$root/backend"
uv run --quiet ruff check src tests migrations scripts
uv run --quiet ruff format --check src tests migrations scripts
uv run --quiet mypy
uv run --quiet pytest -q

echo "== api client"
"$root/scripts/gen-client.sh" >/dev/null
git -C "$root" diff --exit-code -- frontend/openapi.json frontend/src/api/schema.d.ts

echo "== frontend"
cd "$root/frontend"
npm run --silent lint
npm run --silent typecheck
npm test --silent

echo "All checks passed."
