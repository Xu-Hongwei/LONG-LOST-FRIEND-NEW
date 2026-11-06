param([string]$Python = "", [switch]$NoLocalConfig)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

Write-Host "[1/3] Backend offline tests"
$testArguments = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", (Join-Path $PSScriptRoot "test-backend.ps1"))
if ($Python) { $testArguments += @("-Python", $Python) }
if ($NoLocalConfig) { $testArguments += '-NoLocalConfig' }
& powershell @testArguments
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "[2/3] Frontend regression tests"
Push-Location (Join-Path $root "frontend")
try {
    & npm.cmd test
    $frontendTestExitCode = $LASTEXITCODE
} finally { Pop-Location }
if ($frontendTestExitCode -ne 0) { exit $frontendTestExitCode }

Write-Host "[3/3] Frontend type check and production build"
Push-Location (Join-Path $root "frontend")
try {
    & npm.cmd run build
    $buildExitCode = $LASTEXITCODE
} finally {
    Pop-Location
}
if ($buildExitCode -ne 0) { exit $buildExitCode }
Write-Host "All project checks passed."
exit 0
