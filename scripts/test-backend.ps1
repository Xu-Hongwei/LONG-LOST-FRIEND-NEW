param([string]$Python = "")

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $root "backend"
if (-not $Python) {
    if (Test-Path "D:\APP\miniconda3\python.exe") {
        $Python = "D:\APP\miniconda3\python.exe"
    } else {
        $Python = "python"
    }
}

Push-Location $backend
try {
    & $Python -B -m unittest discover -s tests
    $testExitCode = $LASTEXITCODE
} finally {
    Pop-Location
}
exit $testExitCode
