param(
    [switch]$Rebuild
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

# Read .env values for DB connection
$envMap = @{}
if (Test-Path ".env") {
    Get-Content ".env" | ForEach-Object {
        if ($_ -match '^\s*([A-Za-z_][A-Za-z0-9_]*)=(.*)$') {
            $envMap[$matches[1]] = $matches[2].Trim()
        }
    }
}
$pgDb   = if ($envMap["POSTGRES_DB"])       { $envMap["POSTGRES_DB"] }       else { "noka_judge" }
$pgUser = if ($envMap["POSTGRES_USER"])     { $envMap["POSTGRES_USER"] }     else { "noka_user" }
$pgPass = if ($envMap["POSTGRES_PASSWORD"]) { $envMap["POSTGRES_PASSWORD"] } else { "noka_dev_password" }
$dbUrl  = "postgresql://${pgUser}:${pgPass}@postgres:5432/${pgDb}"

# Ensure Docker network exists
$netExists = docker network ls --format "{{.Name}}" | Where-Object { $_ -eq "noka-judge_default" }
if (-not $netExists) {
    docker network create noka-judge_default | Out-Null
}

function Container-Exists($name) {
    return [bool](docker ps -a --format "{{.Names}}" | Where-Object { $_ -eq $name })
}

# 1. Redis
if (-not (Container-Exists "noka-redis")) {
    Write-Host "Creating noka-redis..."
    docker run -d --name noka-redis --restart unless-stopped `
        --network noka-judge_default --network-alias redis `
        -p 6379:6379 redis:7-alpine | Out-Null
} else {
    docker start noka-redis | Out-Null
}

# 2. PostgreSQL (uses persistent named volume noka-judge_postgres_data)
if (-not (Container-Exists "noka-postgres")) {
    Write-Host "Creating noka-postgres..."
    docker run -d --name noka-postgres --restart unless-stopped `
        --network noka-judge_default --network-alias postgres `
        -e POSTGRES_DB=$pgDb -e POSTGRES_USER=$pgUser -e POSTGRES_PASSWORD=$pgPass `
        -v noka-judge_postgres_data:/var/lib/postgresql/data `
        -p 5432:5432 postgres:16-alpine | Out-Null
} else {
    docker start noka-postgres | Out-Null
}

Write-Host "Waiting for PostgreSQL..."
for ($i = 0; $i -lt 30; $i++) {
    docker exec noka-postgres pg_isready -U $pgUser -d $pgDb 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) { break }
    Start-Sleep -Seconds 1
}

# 3. Backend & Judge Worker
$needBackendImg = $Rebuild -or (-not (docker images -q noka-judge-backend:latest))
$needJudgeImg   = $Rebuild -or (-not (docker images -q noka-judge-judge-worker:latest))

if ($needBackendImg) {
    Write-Host "Building backend image..."
    docker build -q -t noka-judge-backend:latest -f backend/Dockerfile . | Out-Null
}
if ($needJudgeImg) {
    Write-Host "Building judge-worker image..."
    docker build -q -t noka-judge-judge-worker:latest -f judge/Dockerfile . | Out-Null
}

if ($Rebuild -or -not (Container-Exists "noka-backend")) {
    if (Container-Exists "noka-backend") { docker rm -f noka-backend | Out-Null }
    Write-Host "Starting noka-backend..."
    docker run -d --name noka-backend --restart unless-stopped `
        --network noka-judge_default --network-alias backend `
        --env-file .env `
        -e APP_ENV=development `
        -e DATABASE_URL=$dbUrl `
        -e REDIS_URL=redis://redis:6379/0 `
        -e STORAGE_LOCAL_PATH=/app/storage `
        -e JUDGE_MODE=local_posix `
        -v noka-judge_storage:/app/storage `
        -p 8000:8000 noka-judge-backend:latest | Out-Null
} else {
    docker start noka-backend | Out-Null
}

if ($Rebuild -or -not (Container-Exists "noka-judge-worker")) {
    if (Container-Exists "noka-judge-worker") { docker rm -f noka-judge-worker | Out-Null }
    Write-Host "Starting noka-judge-worker..."
    docker run -d --name noka-judge-worker --restart unless-stopped `
        --network noka-judge_default `
        --env-file .env `
        -e DATABASE_URL=$dbUrl `
        -e REDIS_URL=redis://redis:6379/0 `
        -e STORAGE_LOCAL_PATH=/app/storage `
        -e JUDGE_MODE=local_posix `
        -v noka-judge_storage:/app/storage `
        noka-judge-judge-worker:latest | Out-Null
} else {
    docker start noka-judge-worker | Out-Null
}

# 4. Frontend (Vite dev server accessible on LAN)
if ($Rebuild -or -not (Container-Exists "noka-frontend")) {
    if (Container-Exists "noka-frontend") { docker rm -f noka-frontend | Out-Null }
    Write-Host "Starting noka-frontend..."
    docker create --name noka-frontend --restart unless-stopped `
        --network noka-judge_default -w /app `
        -e VITE_APP_NAME="Noka JUDGE" `
        -e VITE_PROXY_TARGET=http://backend:8000 `
        -v noka-judge_frontend_node_modules:/app/node_modules `
        -p 5173:5173 node:20-alpine sh -c "npm install && npm run dev -- --host 0.0.0.0" | Out-Null
    docker cp frontend/. noka-frontend:/app/
    docker start noka-frontend | Out-Null
} else {
    docker start noka-frontend | Out-Null
}

# Detect LAN IP
$lanIp = (Get-NetIPAddress -AddressFamily IPv4 |
    Where-Object { $_.InterfaceAlias -notmatch 'Loopback|vEthernet' -and $_.IPAddress -notlike '169.254.*' } |
    Select-Object -First 1 -ExpandProperty IPAddress)

Write-Host ""
Write-Host "Noka JUDGE dang chay!" -ForegroundColor Green
Write-Host "  May nay (Local): http://localhost:5173"
if ($lanIp) {
    Write-Host "  Mang LAN:        http://${lanIp}:5173" -ForegroundColor Cyan
    Write-Host "  Backend API:     http://${lanIp}:8000/docs"
}
Write-Host "  De tat web:      .\stop-web.ps1"
