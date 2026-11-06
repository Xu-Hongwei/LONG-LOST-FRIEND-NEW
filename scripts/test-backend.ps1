param([string]$Python = "", [switch]$NoLocalConfig)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $root "backend"
. (Join-Path $PSScriptRoot 'dev-common.ps1')
Initialize-DevConfig -Python $Python -NoLocalConfig:$NoLocalConfig

Push-Location $backend
try {
    & $script:PythonExe -B -m unittest discover -s tests
    $testExitCode = $LASTEXITCODE
} finally {
    Pop-Location
}
exit $testExitCode
