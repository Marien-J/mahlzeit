#!/usr/bin/env bash
# Back up the database and files into ./backups. Safe while the app runs.
set -euo pipefail
cd "$(dirname "$0")/.."
docker compose --profile ops run --rm -e BACKUP_OWNER="$(id -u):$(id -g)" backup backup.sh
