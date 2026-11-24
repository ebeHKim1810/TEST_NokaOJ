#!/usr/bin/env bash
set -euo pipefail

if [ ! -f .env ]; then
  echo "[Noka JUDGE] .env not found. Copying from .env.example..."
  cp .env.example .env
fi

echo "[Noka JUDGE] Starting development stack..."
docker compose up -d --build
echo "[Noka JUDGE] System started!"
echo "  - Frontend: http://localhost:5173"
echo "  - Backend API Docs: http://localhost:8000/docs"
echo "  - Create first Admin: docker compose exec backend python /app/scripts/create_admin.py"
