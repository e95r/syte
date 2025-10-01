#!/usr/bin/env bash
set -euo pipefail

COMPOSE_CMD=${COMPOSE_CMD:-docker compose}
DB_SERVICE=${DB_SERVICE:-db}
POSTGRES_DB=${POSTGRES_DB:-swimdb}
POSTGRES_USER=${POSTGRES_USER:-swimuser}
OUTPUT_PATH=${1:-backups/$(date +%Y%m%d_%H%M%S)_${POSTGRES_DB}.sql}

mkdir -p "$(dirname "$OUTPUT_PATH")"

>&2 echo "[+] Dumping database '${POSTGRES_DB}' from service '${DB_SERVICE}'..."
$COMPOSE_CMD exec -T "$DB_SERVICE" pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" > "$OUTPUT_PATH"

>&2 echo "[+] Backup created at $OUTPUT_PATH"
