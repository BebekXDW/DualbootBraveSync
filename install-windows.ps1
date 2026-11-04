# Installs Brave Dual-Boot Sync on Windows.
# Run in PowerShell:  powershell -ExecutionPolicy Bypass -File .\install-windows.ps1 -SyncDir D:\brave-sync
param([string]$SyncDir)

$ErrorActionPreference = "Stop"
$ExtId    = "mdbmccmhobidhmobkaiogmiembhamgdf"
$HostName = "com.cookiesync.host"
$Src      = Split-Path -Parent $MyInvocation.MyCommand.Path
$Dest     = Join-Path $env:LOCALAPPDATA "CookieSync"
$Udd      = Join-Path $env:LOCALAPPDATA "BraveSoftware\Brave-Browser\User Data"

if (-not $SyncDir) {
  $SyncDir = Read-Host "Shared folder for Brave sync (same folder Arch uses, e.g. D:\brave-sync)"
}
if ($SyncDir -like "*.json") { $SyncDir = Split-Path -Parent $SyncDir }  # old-style file path

function Write-Json($Object, $Path) {
  # No BOM: Brave's JSON reader is strict about it.
  [IO.File]::WriteAllText($Path, ($Object | ConvertTo-Json -Depth 5), (New-Object Text.UTF8Encoding $false))
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
$Pythonw = Join-Path (Split-Path -Parent $Python) "pythonw.exe"   # runs without a console window
if (-not (Test-Path $Pythonw)) { $Pythonw = $Python }

$Brave = $null
foreach ($base in @($env:ProgramFiles, ${env:ProgramFiles(x86)}, $env:LOCALAPPDATA)) {
  if ($base) {
    $c = Join-Path $base "BraveSoftware\Brave-Browser\Application\brave.exe"
    if (Test-Path $c) { $Brave = $c; break }
  }
}
if (-not $Brave) { Write-Warning "brave.exe not found; set ""brave"" in $Dest\config.json" }

New-Item -ItemType Directory -Force -Path $Dest | Out-Null
Copy-Item (Join-Path $Src "host\cookie_sync_host.py"), (Join-Path $Src "host\profile_sync.py") $Dest -Force

$cfg = [ordered]@{ sync_dir = $SyncDir; user_data_dir = $Udd; profile = "Default" }
if ($Brave) { $cfg.brave = $Brave }
Write-Json $cfg (Join-Path $Dest "config.json")

# Native helper for the extension
$Bat = Join-Path $Dest "cookie_sync_host.bat"
"@echo off`r`n`"$Python`" -u `"%~dp0cookie_sync_host.py`" %*" | Set-Content -Encoding ASCII $Bat
$ManifestPath = Join-Path $Dest "$HostName.json"
Write-Json ([ordered]@{
  name = $HostName
  description = "Brave Dual-Boot Sync helper"
  path = $Bat
  type = "stdio"
  allowed_origins = @("chrome-extension://$ExtId/")
}) $ManifestPath
foreach ($k in @(
  "HKCU:\Software\Google\Chrome\NativeMessagingHosts\$HostName",
  "HKCU:\Software\BraveSoftware\Brave-Browser\NativeMessagingHosts\$HostName"
)) {
  New-Item -Force -Path $k | Out-Null
  Set-ItemProperty -Path $k -Name "(default)" -Value $ManifestPath
}

# Shortcuts
$Shell  = New-Object -ComObject WScript.Shell
$Script = "`"$(Join-Path $Dest 'profile_sync.py')`""
function New-Shortcut($Path, $Arguments) {
  $l = $Shell.CreateShortcut($Path)
  $l.TargetPath = $Pythonw
  $l.Arguments = $Arguments
  $l.WorkingDirectory = $Dest
  if ($Brave) { $l.IconLocation = "$Brave,0" }
  $l.Save()
}
$Desktop   = [Environment]::GetFolderPath("Desktop")
$StartMenu = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs"
$Startup   = [Environment]::GetFolderPath("Startup")
New-Shortcut (Join-Path $Desktop "Brave (Sync).lnk") "$Script launch"
New-Shortcut (Join-Path $StartMenu "Brave (Sync).lnk") "$Script launch"
New-Shortcut (Join-Path $Startup "Brave profile import.lnk") "$Script import"   # at login

if (-not (Test-Path $SyncDir)) { New-Item -ItemType Directory -Force -Path $SyncDir | Out-Null }

Write-Host "Done."
Write-Host "  Helper:     $Dest"
Write-Host "  Python:     $Python"
Write-Host "  Brave:      $Brave"
Write-Host "  Shared dir: $SyncDir"
Write-Host "  Start Brave from the new 'Brave (Sync)' shortcut (pin that one to the taskbar)."
