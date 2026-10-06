#!/usr/bin/env bash
# Restore a backup made by scripts/backup.sh:
#   scripts/restore.sh backups/mahlzeit-<time>.tar.age path/to/age-key.txt
#   scripts/restore.sh backups/mahlzeit-<time>.tar          (unencrypted)
# Stops app and worker, replaces database and files, starts them again and waits for health.
set -euo pipefail
cd "$(dirname "$0")/.."

file="${1:?usage: scripts/restore.sh <backup file> [age identity file]}"
identity="${2:-}"
[ -f "$file" ] || { echo "no such file: $file" >&2; exit 1; }
backup_dir="$(mkdir -p "${BACKUP_DIR:-./backups}" && cd "${BACKUP_DIR:-./backups}" && pwd)"
[ "$(cd "$(dirname "$file")" && pwd)" = "$backup_dir" ] || {
  echo "put the backup into $backup_dir first" >&2
  exit 1
}

args=(--profile ops run --rm)
inner=(restore.sh "/backups/$(basename "$file")")
if [ -n "$identity" ]; then
  args+=(-v "$(cd "$(dirname "$identity")" && pwd)/$(basename "$identity"):/run/age-identity:ro")
  inner+=(/run/age-identity)
fi

docker compose up -d --wait db
docker compose stop app worker
docker compose "${args[@]}" backup "${inner[@]}"
docker compose up -d --wait app worker caddy
echo "Restore complete."
