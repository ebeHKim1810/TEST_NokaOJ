$ErrorActionPreference = "Stop"
if (-Not (Test-Path ".env")) {
    Write-Host "[Noka JUDGE] .env not found. Copying from .env.example..."
    Copy-Item ".env.example" ".env"
}
Write-Host "[Noka JUDGE] Starting development stack on Windows Docker Desktop..."
docker compose up -d --build
Write-Host "[Noka JUDGE] Started! Open http://localhost:5173"
Write-Host "Create first Admin: docker compose exec backend python /app/scripts/create_admin.py"
