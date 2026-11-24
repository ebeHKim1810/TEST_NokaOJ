$ErrorActionPreference = "Stop"
Write-Host "[Noka JUDGE] Stopping all services..."
docker compose down
Write-Host "[Noka JUDGE] Stopped."
