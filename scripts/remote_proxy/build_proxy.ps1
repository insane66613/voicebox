Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Set-Location (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location ..\..

$Venv = ".venv-remote-proxy"
$Python = ".\$Venv\Scripts\python.exe"

if (-not (Test-Path $Python)) {
    py -3.12 -m venv $Venv
}

& $Python -m pip install --upgrade pip
& $Python -m pip install fastapi==0.111.0 "uvicorn[standard]" httpx pyinstaller

$OutDir = "tauri\src-tauri\binaries"
if (-not (Test-Path $OutDir)) {
    New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
}

& $Python -m PyInstaller `
    --onefile `
    --name voicebox-remote-proxy `
    --distpath $OutDir `
    --workpath "build\remote-proxy-pyinstaller" `
    --specpath "build\remote-proxy-pyinstaller" `
    "scripts\remote_proxy\voicebox_remote_proxy.py"

$TargetTriple = rustc --print host-tuple
$Exe = Join-Path $OutDir "voicebox-remote-proxy.exe"
$TauriExe = Join-Path $OutDir "voicebox-remote-proxy-$TargetTriple.exe"

if (Test-Path $TauriExe) {
    Remove-Item $TauriExe -Force
}

Rename-Item $Exe (Split-Path $TauriExe -Leaf)

Write-Host "`nBuilt sidecar:"
Write-Host $TauriExe
