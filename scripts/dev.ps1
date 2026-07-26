<#
.SYNOPSIS
Starts the Paperplane backend and frontend development servers.

.PARAMETER BackendPort
Backend port to use. Zero selects the first free port from 8010 through 8099.

.PARAMETER FrontendPort
Frontend port to use. Zero selects the first free port from 3000 through 3099.
#>
[CmdletBinding()]
param(
    [ValidateRange(0, 65535)]
    [int]$BackendPort = 0,

    [ValidateRange(0, 65535)]
    [int]$FrontendPort = 0
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Test-TcpPortAvailable {
    param([Parameter(Mandatory)][int]$Port)

    $listener = [System.Net.Sockets.TcpListener]::new(
        [System.Net.IPAddress]::Loopback,
        $Port
    )
    try {
        $listener.Start()
        return $true
    }
    catch [System.Net.Sockets.SocketException] {
        return $false
    }
    finally {
        $listener.Stop()
    }
}

function Resolve-DevelopmentPort {
    param(
        [Parameter(Mandatory)][int]$RequestedPort,
        [Parameter(Mandatory)][int]$RangeStart,
        [Parameter(Mandatory)][int]$RangeEnd,
        [Parameter(Mandatory)][string]$Label
    )

    if ($RequestedPort -ne 0) {
        if (-not (Test-TcpPortAvailable -Port $RequestedPort)) {
            throw "$Label port $RequestedPort is already in use."
        }
        return $RequestedPort
    }

    foreach ($candidate in $RangeStart..$RangeEnd) {
        if (Test-TcpPortAvailable -Port $candidate) {
            return $candidate
        }
    }

    throw "No free $Label port was found from $RangeStart through $RangeEnd."
}

function Start-DevelopmentProcess {
    param(
        [Parameter(Mandatory)][string]$FilePath,
        [Parameter(Mandatory)][string[]]$ArgumentList,
        [Parameter(Mandatory)][string]$WorkingDirectory,
        [hashtable]$Environment = @{}
    )

    $startInfo = [System.Diagnostics.ProcessStartInfo]::new()
    $startInfo.FileName = $FilePath
    $startInfo.WorkingDirectory = $WorkingDirectory
    $startInfo.UseShellExecute = $false
    foreach ($argument in $ArgumentList) {
        $startInfo.ArgumentList.Add($argument)
    }
    foreach ($entry in $Environment.GetEnumerator()) {
        $startInfo.Environment[$entry.Key] = $entry.Value
    }

    $process = [System.Diagnostics.Process]::new()
    $process.StartInfo = $startInfo
    if (-not $process.Start()) {
        throw "Failed to start $FilePath."
    }
    return $process
}

function Stop-DevelopmentProcess {
    param([System.Diagnostics.Process]$Process)

    if ($null -eq $Process) {
        return
    }
    try {
        if (-not $Process.HasExited) {
            $Process.Kill($true)
            [void]$Process.WaitForExit(5000)
        }
    }
    catch [System.InvalidOperationException] {
        # The process exited between the state check and the kill request.
    }
    finally {
        $Process.Dispose()
    }
}

function Wait-ForV2Backend {
    param(
        [Parameter(Mandatory)][System.Diagnostics.Process]$Process,
        [Parameter(Mandatory)][string]$Origin
    )

    $deadline = [DateTimeOffset]::UtcNow.AddSeconds(60)
    $openApiUri = "$Origin/openapi.json"
    while ([DateTimeOffset]::UtcNow -lt $deadline) {
        if ($Process.HasExited) {
            throw "Backend exited during startup with code $($Process.ExitCode)."
        }
        try {
            $document = Invoke-RestMethod -Uri $openApiUri -TimeoutSec 2 -NoProxy
        }
        catch {
            Start-Sleep -Milliseconds 250
            continue
        }
        if (
            $document.info.version -eq "2.0.0" -and
            $document.paths.PSObject.Properties.Name -contains "/api/v2/jobs"
        ) {
            return
        }
        throw "The backend on $Origin is not the Paperplane v2 API."
    }

    throw "Backend did not become ready within 60 seconds."
}

function Wait-ForFrontendProxy {
    param(
        [Parameter(Mandatory)][System.Diagnostics.Process]$Process,
        [Parameter(Mandatory)][string]$Origin
    )

    $deadline = [DateTimeOffset]::UtcNow.AddSeconds(60)
    $jobsUri = "$Origin/api/v2/jobs"
    while ([DateTimeOffset]::UtcNow -lt $deadline) {
        if ($Process.HasExited) {
            throw "Frontend exited during startup with code $($Process.ExitCode)."
        }
        try {
            $response = Invoke-WebRequest -Uri $jobsUri -TimeoutSec 2 -NoProxy
        }
        catch {
            Start-Sleep -Milliseconds 250
            continue
        }
        if ($response.StatusCode -eq 200) {
            return
        }
    }

    throw "Frontend proxy did not become ready within 60 seconds."
}

if ([string]::IsNullOrWhiteSpace($env:OPENAI_API_KEY)) {
    throw "OPENAI_API_KEY is not set. Open a new terminal after setting the user variable."
}
if ([string]::IsNullOrWhiteSpace($env:OPENAI_BASE_URL)) {
    throw "OPENAI_BASE_URL is not set. Open a new terminal after setting the user variable."
}

$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$frontendDirectory = Join-Path $repoRoot "frontend"
$uv = (Get-Command uv.exe -ErrorAction Stop).Source
$npm = (Get-Command npm.cmd -ErrorAction Stop).Source

$selectedBackendPort = Resolve-DevelopmentPort `
    -RequestedPort $BackendPort `
    -RangeStart 8010 `
    -RangeEnd 8099 `
    -Label "Backend"
$selectedFrontendPort = Resolve-DevelopmentPort `
    -RequestedPort $FrontendPort `
    -RangeStart 3000 `
    -RangeEnd 3099 `
    -Label "Frontend"

$packageLock = Join-Path $frontendDirectory "package-lock.json"
$dependencyMarker = Join-Path $frontendDirectory "node_modules/.paperplane-package-lock.sha256"
$packageLockHash = (Get-FileHash -LiteralPath $packageLock -Algorithm SHA256).Hash
$installedHash = if (Test-Path -LiteralPath $dependencyMarker) {
    (Get-Content -Raw -LiteralPath $dependencyMarker).Trim()
} else {
    ""
}
if ($installedHash -ne $packageLockHash) {
    Write-Host "Installing frontend dependencies..."
    Push-Location $frontendDirectory
    try {
        & $npm ci
        if ($LASTEXITCODE -ne 0) {
            throw "npm ci failed with code $LASTEXITCODE."
        }
        Set-Content -LiteralPath $dependencyMarker -Value $packageLockHash -NoNewline
    }
    finally {
        Pop-Location
    }
}

$backendProcess = $null
$frontendProcess = $null
$backendOrigin = "http://127.0.0.1:$selectedBackendPort"
$frontendOrigin = "http://127.0.0.1:$selectedFrontendPort"

try {
    Write-Host "Starting Paperplane backend on $backendOrigin..."
    $backendProcess = Start-DevelopmentProcess `
        -FilePath $uv `
        -ArgumentList @(
            "run", "--locked", "uvicorn", "app.main:app",
            "--app-dir", "backend", "--reload", "--reload-dir", "backend",
            "--host", "127.0.0.1", "--port", "$selectedBackendPort"
        ) `
        -WorkingDirectory $repoRoot
    Wait-ForV2Backend -Process $backendProcess -Origin $backendOrigin

    Write-Host "Starting Paperplane frontend on $frontendOrigin..."
    $frontendProcess = Start-DevelopmentProcess `
        -FilePath $npm `
        -ArgumentList @(
            "run", "dev", "--", "--hostname", "127.0.0.1", "--port", "$selectedFrontendPort"
        ) `
        -WorkingDirectory $frontendDirectory `
        -Environment @{ PAPERPLANE_BACKEND_ORIGIN = $backendOrigin }
    Wait-ForFrontendProxy -Process $frontendProcess -Origin $frontendOrigin

    Write-Host ""
    Write-Host "Paperplane is ready: $frontendOrigin"
    Write-Host "Backend API docs: $backendOrigin/docs"
    Write-Host "Press Ctrl+C to stop both servers."

    while ($true) {
        if ($backendProcess.HasExited) {
            throw "Backend exited unexpectedly with code $($backendProcess.ExitCode)."
        }
        if ($frontendProcess.HasExited) {
            throw "Frontend exited unexpectedly with code $($frontendProcess.ExitCode)."
        }
        Start-Sleep -Milliseconds 500
    }
}
finally {
    Stop-DevelopmentProcess -Process $frontendProcess
    Stop-DevelopmentProcess -Process $backendProcess
}
