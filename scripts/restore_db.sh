#!/usr/bin/env bash
set -euo pipefail
if [ $# -lt 1 ]; then
  echo "Usage: $0 <path/to/backup.sql.gz>"
  exit 1
fi
BACKUP_FILE="$1"
if [ ! -f "${BACKUP_FILE}" ]; then
  echo "Error: Backup file '${BACKUP_FILE}' not found."
  exit 1
fi
source .env 2>/dev/null || true
DB_NAME="${POSTGRES_DB:-noka_judge}"
DB_USER="${POSTGRES_USER:-noka_user}"
echo "[Noka JUDGE] Restoring '${BACKUP_FILE}' into database '${DB_NAME}'..."
gunzip -c "${BACKUP_FILE}" | docker compose exec -T postgres psql -U "${DB_USER}" -d "${DB_NAME}"
echo "[Noka JUDGE] Restore completed."
