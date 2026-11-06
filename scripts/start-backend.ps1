param([string]$Python = '', [switch]$NoLocalConfig)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'dev-common.ps1')
Initialize-DevConfig -Python $Python -NoLocalConfig:$NoLocalConfig
Start-DevServices -Services @('backend')
