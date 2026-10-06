#!/usr/bin/env bash
# Regenerate the TypeScript API types from the FastAPI schema.
# CI runs this and fails if the result differs from what is committed.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$root/backend"
ENCRYPTION_KEY=x uv run --quiet python -c \
  "import json; from mahlzeit.main import app; print(json.dumps(app.openapi(), indent=2, sort_keys=True))" \
  > "$root/frontend/openapi.json"
cd "$root/frontend"
npx --no-install openapi-typescript openapi.json -o src/api/schema.d.ts
npx --no-install prettier --log-level warn --write openapi.json src/api/schema.d.ts
