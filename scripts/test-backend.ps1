$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $root "backend"
Set-Location $backend

if (Test-Path "D:\APP\miniconda3\python.exe") {
    $python = "D:\APP\miniconda3\python.exe"
} else {
    $python = "python"
}

& $python -m unittest discover -s tests
