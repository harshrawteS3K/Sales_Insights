# Start FastAPI on 0.0.0.0:8000 for Windows Server UAT (VPN access).
# Run from repo or backend folder. Uses APP_HOST/APP_PORT from .env via run.py.

$ErrorActionPreference = "Stop"
$BackendRoot = Split-Path -Parent $PSScriptRoot
Set-Location $BackendRoot

if (-not (Test-Path ".\venv\Scripts\Activate.ps1")) {
    Write-Error "venv not found. Create with: python -m venv venv && .\venv\Scripts\pip install -r requirements.txt"
}

. .\venv\Scripts\Activate.ps1
Write-Host "Running alembic upgrade head (safe to re-run)..."
alembic upgrade head
Write-Host "Starting API | host from APP_HOST (default 0.0.0.0) port APP_PORT (default 8000)"
python run.py
