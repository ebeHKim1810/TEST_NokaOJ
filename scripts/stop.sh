#!/usr/bin/env bash
set -euo pipefail
echo "[Noka JUDGE] Stopping all services..."
docker compose down
echo "[Noka JUDGE] Stopped."
