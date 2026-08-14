# Start every process the portal needs, in the right order.
# Each process opens in its own PowerShell window so you can read logs
# without docker.
#
# Order:
#   1. Backend (waitress on 127.0.0.1:5000)
#   2. Celery worker      (skipped when REDIS_URL is unset)
#   3. Celery beat        (skipped when REDIS_URL is unset)
#   4. Frontend (Next.js on 127.0.0.1:3000)
#
# Postgres is assumed to be running as a Windows service already (see
# docs/DEPLOYMENT.md). If it isn't, the backend hangs on
# wait-for-db.
#
# Redis is OPTIONAL until the Phase-7 notification work: without
# REDIS_URL the rate limiter falls back to an in-memory store and the
# Celery windows are skipped entirely.

$ErrorActionPreference = "Stop"
$root = (Resolve-Path "$PSScriptRoot\..").Path
$backend = Join-Path $root "backend"
$frontend = Join-Path $root "frontend"

function Start-InNewWindow($title, $workdir, $command) {
    Start-Process powershell.exe -ArgumentList @(
        "-NoExit",
        "-Command",
        "`$Host.UI.RawUI.WindowTitle='$title'; Set-Location '$workdir'; $command"
    ) | Out-Null
}

$waitress = Join-Path $backend ".venv\Scripts\waitress-serve.exe"
$celery = Join-Path $backend ".venv\Scripts\celery.exe"
$listen = if ($env:WAITRESS_LISTEN) { $env:WAITRESS_LISTEN } else { "127.0.0.1:5000" }
$threads = if ($env:WAITRESS_THREADS) { $env:WAITRESS_THREADS } else { "8" }

# Read REDIS_URL from backend\.env if the shell hasn't exported one.
$redisUrl = $env:REDIS_URL
if (-not $redisUrl) {
    $envFile = Join-Path $backend ".env"
    if (Test-Path $envFile) {
        $line = Select-String -Path $envFile -Pattern '^\s*REDIS_URL\s*=' | Select-Object -First 1
        if ($line) { $redisUrl = ($line.Line -split '=', 2)[1].Trim() }
    }
}

Write-Host "Starting backend (waitress)..." -ForegroundColor Cyan
Start-InNewWindow "greentech-backend" $backend `
    "& '$waitress' --listen=$listen --threads=$threads wsgi:app"

Start-Sleep -Seconds 3

if ($redisUrl) {
    Write-Host "Starting Celery worker..." -ForegroundColor Cyan
    Start-InNewWindow "greentech-worker" $backend `
        "& '$celery' -A celery_worker.celery worker --loglevel=info --pool=solo"

    Write-Host "Starting Celery beat..." -ForegroundColor Cyan
    Start-InNewWindow "greentech-beat" $backend `
        "& '$celery' -A celery_worker.celery beat --loglevel=info --schedule=$env:TEMP\celerybeat-schedule"
} else {
    Write-Host "REDIS_URL not set - skipping Celery worker/beat." -ForegroundColor Yellow
    Write-Host "  Scheduled reminders need a broker; install Memurai and set" -ForegroundColor Yellow
    Write-Host "  REDIS_URL in backend\.env when you reach Phase 7." -ForegroundColor Yellow
}

Write-Host "Starting Next.js frontend..." -ForegroundColor Cyan
Start-InNewWindow "greentech-frontend" $frontend `
    "npm start"

Write-Host ""
Write-Host "Windows opened. Tail their output to confirm everything is up."
Write-Host "Backend health:   curl http://127.0.0.1:5000/api/v1/health"
Write-Host "Frontend:         http://127.0.0.1:3000"
