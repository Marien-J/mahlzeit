#!/usr/bin/env bash
# Create .env from .env.example with freshly generated secrets. Refuses to overwrite.
#   scripts/init-env.sh                       local (http://localhost)
#   scripts/init-env.sh mahlzeit.example.org  production domain
set -euo pipefail
cd "$(dirname "$0")/.."
[ -e .env ] && { echo ".env exists; edit it instead." >&2; exit 1; }

domain="${1:-}"
docker image inspect "mahlzeit-app:${MAHLZEIT_TAG:-local}" >/dev/null 2>&1 || docker compose build app
secrets="$(docker compose run --rm --no-deps -T app mahlzeit gen-secrets)"

cp .env.example .env
while IFS='=' read -r key value; do
  sed -i.bak "s|^${key}=.*|${key}=${value}|" .env
done <<< "$secrets"
if [ -n "$domain" ]; then
  sed -i.bak "s|^SITE_ADDRESS=.*|SITE_ADDRESS=${domain}|; s|^BASE_URL=.*|BASE_URL=https://${domain}|" .env
fi
rm -f .env.bak
chmod 600 .env
echo "Wrote .env. Set VAPID_SUBJECT (mailto:you@example.org) and, for backups, BACKUP_AGE_RECIPIENT."
