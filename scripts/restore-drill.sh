#!/usr/bin/env bash
# Prove that backup and restore work, without touching the real stack:
# runs a separate Compose project ("mahlzeit-drill") on other ports with its own volumes,
# creates a user and a file, takes an encrypted backup, wipes everything, restores, and
# checks that the user can sign in and the file is back. Uses the images already built.
set -euo pipefail
cd "$(dirname "$0")/.."

export COMPOSE_PROJECT_NAME=mahlzeit-drill
export HTTP_PORT="${DRILL_HTTP_PORT:-8088}" HTTPS_PORT="${DRILL_HTTPS_PORT:-8448}"
export BACKUP_DIR="$(mktemp -d)"
url="http://localhost:${HTTP_PORT}"
email="drill@example.org"
export MAHLZEIT_PASSWORD="drill password 123"

cleanup() {
  docker compose --profile ops down -v --remove-orphans >/dev/null 2>&1 || true
  rm -rf "$BACKUP_DIR"
}
trap cleanup EXIT
step() { printf '\n== %s\n' "$*"; }
login_status() {
  curl -s -o /dev/null -w '%{http_code}' -H 'Content-Type: application/json' \
    -d "{\"email\":\"$email\",\"password\":\"$MAHLZEIT_PASSWORD\"}" "$url/api/auth/login"
}

step "Throwaway age key"
docker compose --profile ops run --rm --no-deps -T -e OWNER="$(id -u):$(id -g)" backup \
  sh -c 'age-keygen -o /backups/key.txt 2>/dev/null && chown "$OWNER" /backups/key.txt'
export BACKUP_AGE_RECIPIENT="$(grep -o 'age1[0-9a-z]*' "$BACKUP_DIR/key.txt" | head -1)"
[ -n "$BACKUP_AGE_RECIPIENT" ] || { echo "no age recipient" >&2; exit 1; }

step "Start a fresh stack and create data"
docker compose up -d --wait db app worker caddy
docker compose exec -T -e MAHLZEIT_PASSWORD app mahlzeit create-admin --email "$email" --name Drill
docker compose exec -T app sh -c 'echo "drill $(date -u +%s)" > /data/files/drill.txt'
marker="$(docker compose exec -T app cat /data/files/drill.txt)"
[ "$(login_status)" = 200 ] || { echo "login before backup failed" >&2; exit 1; }

step "Encrypted backup"
scripts/backup.sh
backup="$(ls -1t "$BACKUP_DIR"/mahlzeit-*.tar.age | head -1)"
echo "backup: $(basename "$backup") ($(du -h "$backup" | cut -f1))"
[ -r "$backup" ] || { echo "backup is not readable by $(id -un)" >&2; exit 1; }
if tar -tf "$backup" >/dev/null 2>&1; then echo "backup is not encrypted" >&2; exit 1; fi

step "Wipe database and files"
docker compose down -v
docker compose up -d --wait db app worker caddy
[ "$(login_status)" = 401 ] || { echo "data survived the wipe?" >&2; exit 1; }

step "Restore"
scripts/restore.sh "$backup" "$BACKUP_DIR/key.txt"

step "Verify"
status="$(login_status)"
restored="$(docker compose exec -T app cat /data/files/drill.txt)"
echo "login after restore: HTTP $status"
echo "file after restore:  $restored"
[ "$status" = 200 ] && [ "$restored" = "$marker" ] || { echo "RESTORE DRILL FAILED" >&2; exit 1; }
echo
echo "Restore drill passed."
