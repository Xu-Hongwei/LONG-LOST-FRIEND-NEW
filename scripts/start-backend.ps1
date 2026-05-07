$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if (Test-Path "D:\APP\miniconda3\python.exe") {
    $python = "D:\APP\miniconda3\python.exe"
} else {
    $python = "python"
}

& $python "backend\run.py"
