[CmdletBinding(SupportsShouldProcess = $true)]
param([ValidateSet('backend','frontend')][string[]]$Services = @('backend','frontend'))
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'dev-common.ps1')
$operationLock = Enter-DevLock
try {
    $records = @(Read-DevState)
    $remaining = @($records)
    foreach ($record in $records) {
        if ($Services -notcontains $record.service) { continue }
        $process = Get-OwnedProcess $record
        if ($process -and -not $PSCmdlet.ShouldProcess("$($record.service) PID $($record.process_id)", 'Stop project process')) { continue }
        if ($WhatIfPreference) { continue }
        Stop-OwnedProcess $record
        $remaining = @($remaining | Where-Object { $_.process_id -ne $record.process_id })
        Save-DevState $remaining
        Write-Host "$($record.service) stopped (or already exited)."
    }
    if (-not $records.Count) { Write-Host 'No recorded project services. No process was stopped.' }
} finally { $operationLock.Dispose() }
