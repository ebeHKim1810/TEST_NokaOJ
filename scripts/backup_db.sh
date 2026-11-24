#!/usr/bin/env bash
set -euo pipefail
source .env 2>/dev/null || true
DB_NAME="${POSTGRES_DB:-noka_judge}"
DB_USER="${POSTGRES_USER:-noka_user}"
STAMP="$(date +%Y%m%d_%H%M%S)"
OUT="database/backups/${DB_NAME}_${STAMP}.sql.gz"
mkdir -p database/backups
echo "[Noka JUDGE] Backing up PostgreSQL database '${DB_NAME}' to ${OUT}..."
docker compose exec -T postgres pg_dump -U "${DB_USER}" "${DB_NAME}" | gzip > "${OUT}"
echo "[Noka JUDGE] Backup completed: ${OUT}"
