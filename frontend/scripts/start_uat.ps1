# Start Vite on 0.0.0.0:5173 for Windows Server UAT (VPN access).
# Set VITE_API_BASE_URL before running, e.g.:
#   $env:VITE_API_BASE_URL = "http://<SERVER-IP>:8000/api"
# Or copy .env.example -> .env.local and edit.

$ErrorActionPreference = "Stop"
$FrontendRoot = Split-Path -Parent $PSScriptRoot
Set-Location $FrontendRoot

if (-not $env:VITE_API_BASE_URL) {
    Write-Warning "VITE_API_BASE_URL is not set. Falling back to http://localhost:8000/api (local only)."
    Write-Warning "For VPN UAT set: `$env:VITE_API_BASE_URL = 'http://<SERVER-IP>:8000/api'"
}

Write-Host "Starting Vite | host 0.0.0.0 port 5173 | API=$($env:VITE_API_BASE_URL)"
npm run dev
