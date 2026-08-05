# Start Vite on 0.0.0.0:5173 for Windows Server UAT (VPN access).
# API URL: leave VITE_API_BASE_URL unset to auto-use http://<page-hostname>:8000/api
# Optional override:
#   $env:VITE_API_BASE_URL = "http://<API-HOST>:8000/api"

$ErrorActionPreference = "Stop"
$FrontendRoot = Split-Path -Parent $PSScriptRoot
Set-Location $FrontendRoot

if ($env:VITE_API_BASE_URL) {
    Write-Host "Starting Vite | host 0.0.0.0 port 5173 | API override=$($env:VITE_API_BASE_URL)"
} else {
    Write-Host "Starting Vite | host 0.0.0.0 port 5173 | API=auto (same host as browser, port 8000)"
}

npm run dev
