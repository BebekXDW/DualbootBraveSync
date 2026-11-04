# Installs the Cookie Sync helper for Brave on Windows.
# Run in PowerShell:  powershell -ExecutionPolicy Bypass -File .\install-windows.ps1
param([string]$SyncFile)

$ErrorActionPreference = "Stop"
$ExtId    = "mdbmccmhobidhmobkaiogmiembhamgdf"
$HostName = "com.cookiesync.host"
$Src      = Split-Path -Parent $MyInvocation.MyCommand.Path
$Dest     = Join-Path $env:LOCALAPPDATA "CookieSync"

if (-not $SyncFile) {
  $SyncFile = Read-Host "Full path of the shared cookies file (same file Arch uses, e.g. D:\cookie-sync\cookies.json)"
}

# Find a real Python (not the Microsoft Store stub)
$Python = $null
$py = Get-Command py -ErrorAction SilentlyContinue
if ($py) { $Python = (& py -3 -c "import sys; print(sys.executable)").Trim() }
if (-not $Python) {
  $p = Get-Command python -ErrorAction SilentlyContinue
  if ($p -and $p.Source -notlike "*WindowsApps*") { $Python = $p.Source }
}
if (-not $Python) { throw "Python 3 not found. Install it from python.org (tick 'Add to PATH'), then run this again." }

New-Item -ItemType Directory -Force -Path $Dest | Out-Null
Copy-Item (Join-Path $Src "host\cookie_sync_host.py") $Dest -Force

@{ sync_file = $SyncFile } | ConvertTo-Json | Set-Content -Encoding UTF8 (Join-Path $Dest "config.json")

# Launcher Brave runs
$Bat = Join-Path $Dest "cookie_sync_host.bat"
"@echo off`r`n`"$Python`" -u `"%~dp0cookie_sync_host.py`" %*" | Set-Content -Encoding ASCII $Bat

$ManifestPath = Join-Path $Dest "$HostName.json"
@{
  name = $HostName
  description = "Cookie Sync helper"
  path = $Bat
  type = "stdio"
  allowed_origins = @("chrome-extension://$ExtId/")
} | ConvertTo-Json | Set-Content -Encoding UTF8 $ManifestPath

# Brave reads Chrome's registry location; its own key is added too to be safe.
foreach ($k in @(
  "HKCU:\Software\Google\Chrome\NativeMessagingHosts\$HostName",
  "HKCU:\Software\BraveSoftware\Brave-Browser\NativeMessagingHosts\$HostName"
)) {
  New-Item -Force -Path $k | Out-Null
  Set-ItemProperty -Path $k -Name "(default)" -Value $ManifestPath
}

$Folder = Split-Path -Parent $SyncFile
if (-not (Test-Path $Folder)) { New-Item -ItemType Directory -Force -Path $Folder | Out-Null }

Write-Host "Done."
Write-Host "  Helper:    $Dest"
Write-Host "  Python:    $Python"
Write-Host "  Sync file: $SyncFile"
