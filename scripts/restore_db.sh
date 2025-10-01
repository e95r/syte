#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <path-to-backup.sql>" >&2
  exit 1
fi

BACKUP_FILE="$1"
COMPOSE_CMD=${COMPOSE_CMD:-docker compose}
DB_SERVICE=${DB_SERVICE:-db}
POSTGRES_DB=${POSTGRES_DB:-swimdb}
POSTGRES_USER=${POSTGRES_USER:-swimuser}

if [[ ! -f "$BACKUP_FILE" ]]; then
  echo "Backup file '$BACKUP_FILE' not found" >&2
  exit 2
fi

>&2 echo "[+] Restoring database '${POSTGRES_DB}' from $BACKUP_FILE..."
$COMPOSE_CMD exec -T "$DB_SERVICE" psql -U "$POSTGRES_USER" "$POSTGRES_DB" -v ON_ERROR_STOP=1 < "$BACKUP_FILE"

>&2 echo "[+] Restore completed"
