#!/usr/bin/env bash
set -euo pipefail
echo "[Noka JUDGE] Running Alembic database migrations..."
docker compose exec backend sh -c "cd /app/backend && alembic upgrade head"
echo "[Noka JUDGE] Migrations applied successfully."
