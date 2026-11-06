$script:ProjectRoot = Split-Path -Parent $PSScriptRoot
$script:RuntimeDir = Join-Path $script:ProjectRoot 'runtime'
if ($env:CAMPUS_RUNTIME_DIR) { $script:RuntimeDir = [IO.Path]::GetFullPath($env:CAMPUS_RUNTIME_DIR) }
$script:StateFile = Join-Path $script:RuntimeDir 'dev-processes.json'

function Initialize-DevConfig {
    param([string]$Python = '', [switch]$NoLocalConfig)
    $localConfig = Join-Path $script:ProjectRoot 'config.local.ps1'
    if (-not $NoLocalConfig -and (Test-Path -LiteralPath $localConfig)) { . $localConfig }
    if (-not $Python) { $Python = $env:CAMPUS_PYTHON }
    if (-not $Python) {
        $venvPython = Join-Path $script:ProjectRoot '.venv\Scripts\python.exe'
        if (Test-Path -LiteralPath $venvPython) { $Python = $venvPython } else { $Python = 'python' }
    }
    $script:PythonExe = (Get-Command $Python -CommandType Application -ErrorAction Stop | Select-Object -First 1).Source
    $script:BackendPort = Get-DevPort 'CAMPUS_BACKEND_PORT' 8766
    $script:FrontendPort = Get-DevPort 'CAMPUS_FRONTEND_PORT' 5176
    $script:PreviewPort = Get-DevPort 'CAMPUS_PREVIEW_PORT' 4176
    $env:CAMPUS_BACKEND_PORT = [string]$script:BackendPort
    $env:CAMPUS_FRONTEND_PORT = [string]$script:FrontendPort
    $env:CAMPUS_PREVIEW_PORT = [string]$script:PreviewPort
}

function Get-DevPort {
    param([string]$Name, [int]$Default)
    $value = [Environment]::GetEnvironmentVariable($Name)
    if (-not $value) { return $Default }
    $portNumber = 0
    if (-not [int]::TryParse($value, [ref]$portNumber) -or $portNumber -lt 1 -or $portNumber -gt 65535) {
        throw "$Name must be an integer between 1 and 65535."
    }
    return $portNumber
}

function Enter-DevLock {
    New-Item -ItemType Directory -Path $script:RuntimeDir -Force | Out-Null
    try { return [IO.File]::Open((Join-Path $script:RuntimeDir 'dev.lock'), 'OpenOrCreate', 'ReadWrite', 'None') }
    catch { throw 'Another start/stop operation is running. Retry after it finishes.' }
}

function Read-DevState {
    if (-not (Test-Path -LiteralPath $script:StateFile)) { return @() }
    $saved = Get-Content -LiteralPath $script:StateFile -Raw | ConvertFrom-Json
    foreach ($record in $saved) { Write-Output $record }
}

function Save-DevState {
    param([object[]]$Records)
    $temporary = "$($script:StateFile).tmp"
    ConvertTo-Json -InputObject @($Records) -Depth 5 | Set-Content -LiteralPath $temporary -Encoding UTF8
    Move-Item -LiteralPath $temporary -Destination $script:StateFile -Force
}

function Get-OwnedProcess {
    param($Record)
    if ($Record.project_root -ne $script:ProjectRoot) { throw 'Process record belongs to another project; refusing to stop it.' }
    $process = Get-Process -Id $Record.process_id -ErrorAction SilentlyContinue
    if (-not $process) { return $null }
    if ($process.StartTime.ToUniversalTime().Ticks.ToString() -ne $Record.start_ticks -or $process.Path -ne $Record.executable) {
        throw "Process identity changed for $($Record.service); refusing to stop PID $($Record.process_id)."
    }
    return $process
}

function Stop-OwnedProcess {
    param($Record)
    $process = Get-OwnedProcess $Record
    if ($process) {
        $process.Kill()
        if (-not $process.WaitForExit(10000)) { throw "Timed out stopping $($Record.service)." }
    }
}

function Assert-FreePort {
    param([int]$Port)
    $listener = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback, $Port)
    try { $listener.Start() } catch { throw "Port $Port is unavailable. No existing process was stopped." }
    finally { $listener.Stop() }
}

function Wait-DevReady {
    param($Record, [string]$RunId = '')
    $deadline = (Get-Date).AddSeconds(40)
    while ((Get-Date) -lt $deadline) {
        if (-not (Get-OwnedProcess $Record)) { throw "$($Record.service) exited. See $($Record.stderr)." }
        try {
            if ($RunId) {
                $health = Invoke-RestMethod -Uri "http://127.0.0.1:$($Record.port)/api/health" -TimeoutSec 2
                if ($health.ok -and $health.instance_id -eq $RunId) { return }
            } else {
                $response = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$($Record.port)/" -TimeoutSec 2
                if ($response.StatusCode -eq 200) { return }
            }
        } catch { }
        Start-Sleep -Milliseconds 250
    }
    throw "$($Record.service) did not become ready. See $($Record.stderr)."
}

function Start-DevServices {
    param([string[]]$Services, [switch]$Preview)
    $operationLock = Enter-DevLock
    $created = @()
    $records = @()
    try {
        $records = @(Read-DevState)
        foreach ($service in $Services) {
            foreach ($record in @($records | Where-Object { $_.service -eq $service })) {
                if (Get-OwnedProcess $record) { throw "$service is already running. Use stop-dev.ps1 first." }
            }
        }
        $frontPort = if ($Preview) { $script:PreviewPort } else { $script:FrontendPort }
        if ($Services -contains 'backend' -and $Services -contains 'frontend' -and $script:BackendPort -eq $frontPort) {
            throw 'Backend and frontend ports must be different.'
        }
        if ($Services -contains 'backend') {
            & $script:PythonExe -B (Join-Path $PSScriptRoot 'check-env.py')
            if ($LASTEXITCODE -ne 0) { throw 'Backend environment check failed.' }
            Assert-FreePort $script:BackendPort
        }
        if ($Services -contains 'frontend') {
            $nodeExe = (Get-Command node -CommandType Application -ErrorAction Stop | Select-Object -First 1).Source
            $vite = Join-Path $script:ProjectRoot 'frontend\node_modules\vite\bin\vite.js'
            if (-not (Test-Path -LiteralPath $vite)) { throw 'Frontend dependencies missing. Run npm ci in frontend.' }
            if ($Preview -and -not (Test-Path (Join-Path $script:ProjectRoot 'frontend\dist\index.html'))) {
                throw 'Preview requires a production build. Run npm run build in frontend.'
            }
            Assert-FreePort $frontPort
        }
        $runId = [guid]::NewGuid().ToString('N')
        $env:CAMPUS_RUN_ID = $runId
        $env:PYTHONUNBUFFERED = '1'
        $env:PYTHONIOENCODING = 'utf-8'
        $logDir = Join-Path $script:RuntimeDir ('logs\' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + $runId.Substring(0,8))
        New-Item -ItemType Directory -Path $logDir -Force | Out-Null
        foreach ($service in $Services) {
            $records = @($records | Where-Object { $_.service -ne $service })
            if ($service -eq 'backend') {
                $executable = $script:PythonExe
                $arguments = @('-B', ('"' + (Join-Path $script:ProjectRoot 'backend\run.py') + '"'))
                $working = $script:ProjectRoot
                $port = $script:BackendPort
            } else {
                $executable = $nodeExe
                $arguments = @(('"' + $vite + '"'))
                if ($Preview) { $arguments += 'preview' }
                $working = Join-Path $script:ProjectRoot 'frontend'
                $port = $frontPort
            }
            $stdout = Join-Path $logDir "$service.out.log"
            $stderr = Join-Path $logDir "$service.err.log"
            $process = Start-Process -FilePath $executable -ArgumentList $arguments -WorkingDirectory $working -WindowStyle Hidden -PassThru -RedirectStandardOutput $stdout -RedirectStandardError $stderr
            $record = [pscustomobject]@{
                service=$service; process_id=$process.Id; start_ticks=$process.StartTime.ToUniversalTime().Ticks.ToString()
                executable=$executable; project_root=$script:ProjectRoot; port=$port; stdout=$stdout; stderr=$stderr
            }
            $created += $record
            $records += $record
            Save-DevState $records
            if ($service -eq 'backend') { Wait-DevReady $record $runId } else { Wait-DevReady $record }
        }
        if ($Services -contains 'backend' -and $Services -contains 'frontend') {
            Wait-DevReady ($created | Where-Object { $_.service -eq 'frontend' }) $runId
        }
        foreach ($record in $created) { Write-Host "$($record.service) ready: http://127.0.0.1:$($record.port)" }
        Write-Host "Logs: $logDir"
    } catch {
        $failure = $_
        foreach ($record in $created) {
            try {
                Stop-OwnedProcess $record
                $records = @($records | Where-Object { $_.process_id -ne $record.process_id })
            } catch { Write-Warning "Rollback could not stop $($record.service); its process record is retained." }
        }
        if ($created.Count) { Save-DevState $records }
        throw $failure
    } finally { $operationLock.Dispose() }
}
