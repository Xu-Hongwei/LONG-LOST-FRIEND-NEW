$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$backendScript = Join-Path $PSScriptRoot "start-backend.ps1"
$frontendScript = Join-Path $PSScriptRoot "start-frontend.ps1"

Start-Process -WindowStyle Hidden -FilePath "powershell" -ArgumentList "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "`"$backendScript`""
Start-Process -WindowStyle Hidden -FilePath "powershell" -ArgumentList "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "`"$frontendScript`""

Write-Host "Backend:  http://127.0.0.1:8766"
Write-Host "Frontend: http://127.0.0.1:5176"
Write-Host "Project:  $root"
Write-Host "Stop:     powershell -NoProfile -ExecutionPolicy Bypass -File scripts\stop-dev.ps1"
