[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [int[]]$Ports = @(8766, 5176)
)

$ErrorActionPreference = "Stop"

function Get-ListeningProcessIds {
    param([int]$Port)

    try {
        return @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction Stop |
            Select-Object -ExpandProperty OwningProcess -Unique)
    } catch {
        $lines = @(netstat -ano -p tcp | Select-String "LISTENING" | Select-String ":$Port\s")
        return @($lines | ForEach-Object {
            $parts = ($_ -replace "^\s+", "") -split "\s+"
            if ($parts.Length -ge 5) { [int]$parts[-1] }
        } | Select-Object -Unique)
    }
}

$foundAny = $false

foreach ($port in $Ports) {
    $processIds = @(Get-ListeningProcessIds -Port $port | Where-Object { $_ -and $_ -gt 0 } | Select-Object -Unique)
    if (-not $processIds -or $processIds.Count -eq 0) {
        Write-Host "No listening process found on port $port."
        continue
    }

    foreach ($processId in $processIds) {
        $process = Get-Process -Id $processId -ErrorAction SilentlyContinue
        if (-not $process) {
            Write-Host "Process $processId for port $port is already gone."
            continue
        }

        $foundAny = $true
        $target = "$($process.ProcessName) pid=$processId port=$port"
        if ($PSCmdlet.ShouldProcess($target, "Stop")) {
            Stop-Process -Id $processId -Force
            Write-Host "Stopped $target."
        }
    }
}

if (-not $foundAny) {
    Write-Host "No frontend/backend dev processes were running."
}
