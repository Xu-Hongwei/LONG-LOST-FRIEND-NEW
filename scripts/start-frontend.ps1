param([string]$Python = '', [switch]$Preview, [switch]$NoLocalConfig)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'dev-common.ps1')
Initialize-DevConfig -Python $Python -NoLocalConfig:$NoLocalConfig
Start-DevServices -Services @('frontend') -Preview:$Preview
