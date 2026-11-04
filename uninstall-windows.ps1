# Removes Brave Dual-Boot Sync from Windows. Your Brave profile is left as it is.
# Run in PowerShell:  powershell -ExecutionPolicy Bypass -File .\uninstall-windows.ps1 [-Purge]
#   -Purge  also delete the synced data (cookies, profile snapshot) from the
#           shared folder. Do this only once you've removed it on Arch too.
param([switch]$Purge)

$ErrorActionPreference = "Stop"
$HostName = "com.cookiesync.host"
$Dest     = Join-Path $env:LOCALAPPDATA "CookieSync"

if (Get-Process brave -ErrorAction SilentlyContinue) {
  throw "Brave is running. Close it first so the launcher isn't removed mid-session."
}

# Shared folder, read before the config is deleted
$SyncDir = $null
$cfgPath = Join-Path $Dest "config.json"
if (Test-Path $cfgPath) {
  $cfg = Get-Content -Raw $cfgPath | ConvertFrom-Json
  if ($cfg.sync_dir) { $SyncDir = $cfg.sync_dir } elseif ($cfg.sync_file) { $SyncDir = Split-Path -Parent $cfg.sync_file }
}

# Shortcuts
foreach ($lnk in @(
  (Join-Path ([Environment]::GetFolderPath("Desktop")) "Brave (Sync).lnk"),
  (Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Brave (Sync).lnk"),
  (Join-Path ([Environment]::GetFolderPath("Startup")) "Brave profile import.lnk")
)) {
  if (Test-Path $lnk) { Remove-Item $lnk -Force; Write-Host "Removed $lnk" }
}

# Native helper registration
foreach ($k in @(
  "HKCU:\Software\Google\Chrome\NativeMessagingHosts\$HostName",
  "HKCU:\Software\BraveSoftware\Brave-Browser\NativeMessagingHosts\$HostName"
)) {
  if (Test-Path $k) { Remove-Item $k -Recurse -Force; Write-Host "Removed $k" }
}

# Keep the profile backups unless purging
if (Test-Path $Dest) {
  $backups = @("backup", "backup.old") | ForEach-Object { Join-Path $Dest $_ } | Where-Object { Test-Path $_ }
  if (-not $Purge -and $backups) {
    $Keep = Join-Path $env:USERPROFILE ("brave-sync-backup-" + (Get-Date -Format "yyyyMMdd-HHmmss"))
    New-Item -ItemType Directory -Force -Path $Keep | Out-Null
    foreach ($b in $backups) { Move-Item $b $Keep }
    Write-Host "Kept profile backups in $Keep"
  }
  Remove-Item $Dest -Recurse -Force
  Write-Host "Removed $Dest"
}

if ($Purge -and $SyncDir -and (Test-Path $SyncDir)) {
  foreach ($n in @("cookies.json", "cookies.json.bak", "cookies.json.tmp", "profile", "profile.bak", "profile.new")) {
    $p = Join-Path $SyncDir $n
    if (Test-Path $p) { Remove-Item $p -Recurse -Force }
  }
  if (-not (Get-ChildItem $SyncDir -Force)) { Remove-Item $SyncDir -Force }
  Write-Host "Deleted synced data in $SyncDir"
} elseif ($SyncDir) {
  Write-Host "Synced data left in $SyncDir (run with -Purge to delete it)"
}

Write-Host ""
Write-Host "Done. Last steps: open brave://extensions and remove ""Brave Dual-Boot Sync"","
Write-Host "and pin the normal Brave icon again if you had replaced it."
