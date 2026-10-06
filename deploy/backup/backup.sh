#!/bin/sh
# Runs inside the backup container. Writes /backups/mahlzeit-<UTC time>.tar[.age] holding
# db.dump (pg_dump custom format), files.tar.gz (the files volume) and meta.txt.
set -eu

: "${POSTGRES_USER:?}" "${POSTGRES_PASSWORD:?}" "${POSTGRES_DB:?}"
export PGPASSWORD="$POSTGRES_PASSWORD"
keep="${BACKUP_KEEP:-14}"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

pg_dump -h db -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc -f "$work/db.dump"
tar -C /data/files -czf "$work/files.tar.gz" .
{
  echo "created=$stamp"
  echo "database=$POSTGRES_DB"
  echo "postgres=$(pg_dump --version)"
} > "$work/meta.txt"

mkdir -p /backups
if [ -n "${BACKUP_AGE_RECIPIENT:-}" ]; then
  out="/backups/mahlzeit-$stamp.tar.age"
  tar -C "$work" -cf - meta.txt db.dump files.tar.gz | age -r "$BACKUP_AGE_RECIPIENT" -o "$out.part"
else
  out="/backups/mahlzeit-$stamp.tar"
  echo "WARNING: BACKUP_AGE_RECIPIENT is not set; this backup is NOT encrypted." >&2
  echo "         Encrypt it before it leaves this machine." >&2
  tar -C "$work" -cf "$out.part" meta.txt db.dump files.tar.gz
fi
mv "$out.part" "$out"
chmod 600 "$out"

# Keep the newest $keep backups.
ls -1t /backups/mahlzeit-*.tar /backups/mahlzeit-*.tar.age 2>/dev/null | tail -n +"$((keep + 1))" | xargs -r rm -f

echo "$out"
