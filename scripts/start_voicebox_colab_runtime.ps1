param([switch]$ForceRemoteRepair)
$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent $PSScriptRoot
$Session = 'voicebox'
$RuntimeDir = Join-Path $PSScriptRoot '.runtime'
$ProxyConfig = Join-Path $env:APPDATA 'sh.voicebox.app\remote_proxy.json'
$TunnelPattern = 'https://[a-zA-Z0-9-]+\.trycloudflare\.com'
New-Item -ItemType Directory -Force -Path $RuntimeDir | Out-Null

function Invoke-Colab([string[]]$ColabArgs, [switch]$AllowFailure, [int]$LocalTimeoutSeconds = 180) {
    $remoteTimeoutIndex = [Array]::IndexOf($ColabArgs, '--timeout')
    if ($remoteTimeoutIndex -ge 0 -and $remoteTimeoutIndex + 1 -lt $ColabArgs.Count) {
        $remoteTimeout = 0
        if ([int]::TryParse($ColabArgs[$remoteTimeoutIndex + 1], [ref]$remoteTimeout)) {
            $LocalTimeoutSeconds = [Math]::Max($LocalTimeoutSeconds, $remoteTimeout + 30)
        }
    }
    $id = [guid]::NewGuid().ToString('N')
    $stdout = Join-Path $RuntimeDir "colab-$id.out"
    $stderr = Join-Path $RuntimeDir "colab-$id.err"
    $colabExe = (Get-Command colab -ErrorAction Stop).Source
    $proc = Start-Process -FilePath $colabExe -ArgumentList $ColabArgs -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru -WindowStyle Hidden
    try {
        if (-not $proc.WaitForExit($LocalTimeoutSeconds * 1000)) {
            $proc.Kill($true)
            $proc.WaitForExit()
            $text = ((Get-Content $stdout,$stderr -Raw -ErrorAction SilentlyContinue) | Out-String)
            throw "colab $($ColabArgs -join ' ') exceeded local timeout of $LocalTimeoutSeconds seconds:`n$text"
        }
        $text = ((Get-Content $stdout,$stderr -Raw -ErrorAction SilentlyContinue) | Out-String)
        $code = $proc.ExitCode
        if ($code -ne 0 -and -not $AllowFailure) {
            throw "colab $($ColabArgs -join ' ') failed ($code):`n$text"
        }
        return [pscustomobject]@{ Code = $code; Text = $text }
    } finally {
        Remove-Item $stdout,$stderr -Force -ErrorAction SilentlyContinue
    }
}

function Invoke-ColabWithRetry([string[]]$ColabArgs, [int]$MaxAttempts = 3) {
    for ($attempt = 1; $attempt -le $MaxAttempts; $attempt++) {
        $result = Invoke-Colab $ColabArgs -AllowFailure
        if ($result.Code -eq 0) { return $result }
        $transient = $result.Text -match '(?i)(429|500|502|503|504|temporar|unavailable|timed? out|timeout|connection.*(reset|closed|aborted))'
        if (-not $transient -or $attempt -eq $MaxAttempts) {
            throw "colab $($ColabArgs -join ' ') failed after $attempt attempt(s) ($($result.Code)):`n$($result.Text)"
        }
        Start-Sleep -Seconds ([Math]::Min(8, [Math]::Pow(2, $attempt)))
    }
}

function Convert-ToWslPath([string]$Path) {
    $full = [IO.Path]::GetFullPath($Path)
    if ($full -notmatch '^([A-Za-z]):\\(.*)$') { throw "Unsupported path: $full" }
    return "/mnt/$($Matches[1].ToLower())/$($Matches[2].Replace('\','/'))"
}

function Ensure-ColabSession {
    $sessions = (Invoke-Colab @('sessions')).Text
    if ($sessions -match '\[voicebox\]') { return }
    if ($sessions -match '\[\?\]') {
        throw 'Refusing to create/stop an anonymous Colab assignment; resolve it explicitly first.'
    }
    Write-Host 'Creating voicebox T4 session...'
    $colabExe = (Get-Command colab -ErrorAction Stop).Source
    $creator = Start-Process -FilePath $colabExe -ArgumentList @('new','--session',$Session,'--gpu','T4') -PassThru -WindowStyle Hidden
    try {
        for ($i = 0; $i -lt 60; $i++) {
            Start-Sleep -Seconds 2
            $probe = Invoke-Colab @('sessions') -AllowFailure
            if ($probe.Code -eq 0 -and $probe.Text -match '\[voicebox\]') { return }
            if ($creator.HasExited -and $creator.ExitCode -ne 0) {
                throw "colab new exited with code $($creator.ExitCode) before voicebox appeared."
            }
        }
        throw 'Timed out waiting for the newly allocated voicebox Colab session.'
    } finally {
        if ($creator -and -not $creator.HasExited) { Stop-Process -Id $creator.Id -Force -ErrorAction SilentlyContinue }
    }
}
function Get-LiveTunnel {
    $probeFile = Convert-ToWslPath (Join-Path $PSScriptRoot '_colab_poll_probe.py')
    $probe = Invoke-Colab @('exec','--session',$Session,'--file',$probeFile,'--timeout','60') -AllowFailure
    if ($probe.Code -eq 0 -and $probe.Text -match $TunnelPattern -and $probe.Text -match 'REMOTE_POLL 200') {
        return [regex]::Match($probe.Text, $TunnelPattern).Value
    }
    return $null
}

function Ensure-RemoteGoogleDriveState {
    $probe = Convert-ToWslPath (Join-Path $PSScriptRoot '_colab_drive_ready_probe.py')
    $state = Invoke-Colab @('exec','--session',$Session,'--file',$probe,'--timeout','60') -AllowFailure
    if ($state.Code -eq 0 -and $state.Text -match 'REMOTE_DRIVE_READY') { return }
    Write-Host 'Mounting persistent Google Drive state...'
    $mount = Invoke-Colab @('drivemount','--session',$Session,'/content/drive') -AllowFailure
    $state = Invoke-Colab @('exec','--session',$Session,'--file',$probe,'--timeout','60') -AllowFailure
    if ($mount.Code -eq 0 -and $state.Code -eq 0 -and $state.Text -match 'REMOTE_DRIVE_READY') { return }
    throw @"
Google Drive persistent state could not be mounted for the Colab 'voicebox' session.
Voicebox will not start against ephemeral /content data.
Complete the state-bound Drive authorization for this T4, then retry the launcher.
"@
}

function Install-RemoteRuntime {
    Write-Host 'Installing current backend source into Colab...'
    $bundle = Join-Path $RuntimeDir 'voicebox-backend.zip'
    $stageRoot = Join-Path $RuntimeDir 'bundle-stage'
    $stageBackend = Join-Path $stageRoot 'backend'
    Remove-Item $bundle,$stageRoot -Recurse -Force -ErrorAction SilentlyContinue
    New-Item -ItemType Directory -Force -Path $stageBackend | Out-Null
    & robocopy (Join-Path $RepoRoot 'backend') $stageBackend /E /XD venv build dist __pycache__ .pytest_cache tests /XF *.pyc *.pyo | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "robocopy backend staging failed ($LASTEXITCODE)" }
    Compress-Archive -Path $stageBackend -DestinationPath $bundle -CompressionLevel Fastest
    Remove-Item $stageRoot -Recurse -Force
    $bundleWsl = Convert-ToWslPath $bundle
    Invoke-ColabWithRetry @('upload','--session',$Session,$bundleWsl,'/content/voicebox-backend.zip') | Out-Null
    $installer = Convert-ToWslPath (Join-Path $PSScriptRoot '_colab_install_runtime_bundle.py')
    Invoke-ColabWithRetry @('exec','--session',$Session,'--file',$installer,'--timeout','120') | Out-Null
    $repair = Convert-ToWslPath (Join-Path $PSScriptRoot 'colab_live_repair.py')
    $result = Invoke-Colab @('exec','--session',$Session,'--file',$repair,'--timeout','900')
    if ($result.Text -notmatch $TunnelPattern) { throw 'Colab repair completed without a tunnel URL.' }
    return [regex]::Matches($result.Text, $TunnelPattern)[-1].Value
}

function Set-ProxyConfig([string]$Tunnel) {
    $dir = Split-Path -Parent $ProxyConfig
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    $config = @{ upstream_url=$Tunnel; health=@{status='healthy'; model_loaded=$false; gpu_available=$false} }
    $config | ConvertTo-Json -Depth 4 | Set-Content -Path $ProxyConfig -Encoding utf8
}
function Test-Http([string]$Url) {
    try { return (Invoke-WebRequest $Url -UseBasicParsing -TimeoutSec 10).StatusCode -eq 200 }
    catch { return $false }
}

function Ensure-LocalProxy([string]$Tunnel) {
    Set-ProxyConfig $Tunnel
    $sse = (& curl.exe -sN --max-time 12 'http://127.0.0.1:17493/events/speak' 2>$null | Out-String)
    if ((Test-Http 'http://127.0.0.1:17493/profiles') -and $sse -match 'event: ping') { return }
    $listener = Get-NetTCPConnection -LocalPort 17493 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($listener) {
        $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$($listener.OwningProcess)"
        if ($proc.CommandLine -notmatch 'voicebox[_-]remote[_-]proxy|voicebox-remote-proxy') {
            throw "Port 17493 is owned by an unrelated process: $($proc.CommandLine)"
        }
        Stop-Process -Id $listener.OwningProcess -Force
        Start-Sleep -Seconds 1
    }
    $proxy = Join-Path $RepoRoot 'scripts\remote_proxy\voicebox_remote_proxy.py'
    Start-Process python -ArgumentList @($proxy,'--upstream-url',$Tunnel,'--host','127.0.0.1','--port','17493') -WorkingDirectory $RepoRoot -WindowStyle Hidden
    for ($i=0; $i -lt 30; $i++) {
        if (Test-Http 'http://127.0.0.1:17493/profiles') { return }
        Start-Sleep -Seconds 1
    }
    throw 'Local Voicebox proxy did not become healthy.'
}

function Ensure-TauriVite([string]$Tunnel) {
    $entry = $null
    try { $entry = (Invoke-WebRequest 'http://127.0.0.1:5174/src/main.tsx' -UseBasicParsing -TimeoutSec 4).Content } catch {}
    if ($entry -match 'PlatformProvider') { return }
    $listener = Get-NetTCPConnection -LocalPort 5174 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($listener) {
        $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$($listener.OwningProcess)"
        if ($proc.Name -ne 'node.exe') { throw "Port 5174 is owned by $($proc.Name); refusing to terminate it." }
        Stop-Process -Id $listener.OwningProcess -Force
        Start-Sleep -Seconds 1
    }
    $old = $env:VITE_VOICEBOX_REMOTE_UPSTREAM_URL
    $env:VITE_VOICEBOX_REMOTE_UPSTREAM_URL = $Tunnel
    try {
        Start-Process cmd.exe -ArgumentList @('/c','bun run dev -- --host 127.0.0.1') -WorkingDirectory (Join-Path $RepoRoot 'tauri') -WindowStyle Hidden
    } finally { $env:VITE_VOICEBOX_REMOTE_UPSTREAM_URL = $old }
    for ($i=0; $i -lt 30; $i++) {
        try { $entry = (Invoke-WebRequest 'http://127.0.0.1:5174/src/main.tsx' -UseBasicParsing -TimeoutSec 3).Content } catch { $entry = '' }
        if ($entry -match 'PlatformProvider') { return }
        Start-Sleep -Seconds 1
    }
    throw 'Tauri-root Vite did not become ready.'
}

Ensure-ColabSession
Ensure-RemoteGoogleDriveState
$Tunnel = if ($ForceRemoteRepair) { $null } else { Get-LiveTunnel }
if (-not $Tunnel) {
    $sessions = (Invoke-Colab @('sessions')).Text
    if ($sessions -notmatch '\[voicebox\]') { Ensure-ColabSession }
    $Tunnel = Install-RemoteRuntime
}
Write-Host "Voicebox tunnel: $Tunnel"
Ensure-LocalProxy $Tunnel
Ensure-TauriVite $Tunnel

Get-Process voicebox -ErrorAction SilentlyContinue | Stop-Process -Force
$exe = Join-Path $RepoRoot 'tauri\src-tauri\target\debug\voicebox.exe'
if (-not (Test-Path $exe)) { throw "Voicebox desktop binary not found: $exe" }
Start-Process $exe -WorkingDirectory (Split-Path -Parent $exe)
for ($i=0; $i -lt 30; $i++) {
    $p = Get-Process voicebox -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($p -and $p.MainWindowHandle -ne 0 -and (Test-Http 'http://127.0.0.1:5174/')) { break }
    Start-Sleep -Seconds 1
}
if (-not $p -or $p.MainWindowHandle -eq 0) { throw 'Voicebox desktop window did not become visible.' }
# Reassert the verified tunnel after GUI startup so stale client state cannot
# redirect the local proxy back to a previous Quick Tunnel.
Set-ProxyConfig $Tunnel
$sse = (& curl.exe -sN --max-time 12 'http://127.0.0.1:17493/events/speak' 2>$null | Out-String)
if ($sse -notmatch 'event: ready' -or $sse -notmatch 'event: ping') { throw 'Speak-event heartbeat verification failed.' }
if (-not (Test-Http 'http://127.0.0.1:17493/profiles')) { throw 'Proxy profile verification failed.' }
Write-Host 'VOICEBOX_COLAB_RUNTIME_OK'
Write-Host "Desktop PID: $($p.Id)"
Write-Host "Upstream: $Tunnel"
