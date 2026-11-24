$ErrorActionPreference = "SilentlyContinue"

$containers = @("noka-frontend", "noka-judge-worker", "noka-backend", "noka-redis", "noka-postgres")
Write-Host "Dang tat Noka JUDGE (du lieu database & bai tap van duoc giu nguyen)..."
foreach ($c in $containers) {
    $exists = docker ps -q --filter "name=^/${c}$"
    if ($exists) {
        docker stop $c | Out-Null
        Write-Host "  Da tat $c"
    }
}
Write-Host "Da tat toan bo he thong. Chay lai bang lenh: .\start-web.ps1" -ForegroundColor Yellow
