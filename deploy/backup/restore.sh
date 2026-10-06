#!/bin/sh
# Runs inside the backup container: restore.sh <backup file in /backups> [age identity file]
# Replaces the database and the files volume. The app and worker must be stopped.
set -eu

: "${POSTGRES_USER:?}" "${POSTGRES_PASSWORD:?}" "${POSTGRES_DB:?}"
export PGPASSWORD="$POSTGRES_PASSWORD"
file="${1:?usage: restore.sh <backup file> [identity file]}"
identity="${2:-}"
[ -f "$file" ] || { echo "no such backup: $file" >&2; exit 1; }
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

case "$file" in
  *.age)
    [ -n "$identity" ] || { echo "encrypted backup: pass the age identity (private key) file" >&2; exit 1; }
    age -d -i "$identity" "$file" | tar -C "$work" -xf - ;;
  *)
    tar -C "$work" -xf "$file" ;;
esac
for part in meta.txt db.dump files.tar.gz; do
  [ -f "$work/$part" ] || { echo "backup is missing $part" >&2; exit 1; }
done
cat "$work/meta.txt"

# Validate the dump before touching the live database.
pg_restore --list "$work/db.dump" > /dev/null

psql -h db -U "$POSTGRES_USER" -d postgres -v ON_ERROR_STOP=1 \
  -c "DROP DATABASE IF EXISTS \"$POSTGRES_DB\" WITH (FORCE)" \
  -c "CREATE DATABASE \"$POSTGRES_DB\""
pg_restore -h db -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner --exit-on-error "$work/db.dump"

find /data/files -mindepth 1 -delete
tar -C /data/files -xzf "$work/files.tar.gz"
chown -R 10001:10001 /data/files

echo "restored $file"
