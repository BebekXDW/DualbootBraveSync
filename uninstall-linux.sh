#!/usr/bin/env bash
# Removes Brave Dual-Boot Sync from Linux. Your Brave profile is left as it is.
# Usage: ./uninstall-linux.sh [--purge]
#   --purge  also delete the synced data (cookies, profile snapshot) from the
#            shared folder. Do this only once you've removed it on Windows too.
set -euo pipefail

HOST_NAME="com.cookiesync.host"
DEST="$HOME/.local/share/cookie-sync"
UDD="${BRAVE_USER_DATA:-$HOME/.config/BraveSoftware/Brave-Browser}"
MANIFEST_DIR="${MANIFEST_DIR:-$UDD/NativeMessagingHosts}"
LAUNCHER="$HOME/.local/bin/brave-sync"
APPS="$HOME/.local/share/applications"
UNIT="$HOME/.config/systemd/user/brave-profile-import.service"

PURGE=0
case "${1:-}" in
  --purge) PURGE=1 ;;
  "") ;;
  *) echo "Usage: $0 [--purge]"; exit 2 ;;
esac

if pgrep -x brave >/dev/null 2>&1; then
  echo "Brave is running. Close it first so the launcher isn't removed mid-session."; exit 1
fi

# Shared folder, read before the config is deleted
SYNC_DIR=""
if [ -f "$DEST/config.json" ]; then
  SYNC_DIR="$(python3 -c 'import json,os,sys; c=json.load(open(sys.argv[1], encoding="utf-8-sig")); print(c.get("sync_dir") or os.path.dirname(c.get("sync_file","")))' "$DEST/config.json" 2>/dev/null || true)"
fi

# Login service
if [ -f "$UNIT" ]; then
  systemctl --user disable brave-profile-import.service >/dev/null 2>&1 || true
  rm -f "$UNIT"
  systemctl --user daemon-reload >/dev/null 2>&1 || true
  echo "Removed login service"
fi

# Menu entry overrides (only ours: they point at the launcher)
for f in "$APPS/brave-browser.desktop" "$APPS/brave.desktop"; do
  if [ -f "$f" ] && grep -q "$LAUNCHER" "$f"; then rm -f "$f"; echo "Restored menu entry $(basename "$f")"; fi
done
command -v update-desktop-database >/dev/null && update-desktop-database "$APPS" 2>/dev/null || true

rm -f "$LAUNCHER" "$MANIFEST_DIR/$HOST_NAME.json"
echo "Removed launcher and native helper registration"

# Keep the profile backups unless purging
if [ -d "$DEST" ]; then
  if [ "$PURGE" = 0 ] && { [ -d "$DEST/backup" ] || [ -d "$DEST/backup.old" ]; }; then
    KEEP="$HOME/brave-sync-backup-$(date +%Y%m%d-%H%M%S)"
    mkdir -p "$KEEP"
    for b in backup backup.old; do [ -d "$DEST/$b" ] && mv "$DEST/$b" "$KEEP/"; done
    echo "Kept profile backups in $KEEP"
  fi
  rm -rf "$DEST"
  echo "Removed $DEST"
fi

if [ "$PURGE" = 1 ] && [ -n "$SYNC_DIR" ] && [ -d "$SYNC_DIR" ]; then
  rm -rf "$SYNC_DIR/cookies.json" "$SYNC_DIR/cookies.json.bak" "$SYNC_DIR/cookies.json.tmp" \
         "$SYNC_DIR/profile" "$SYNC_DIR/profile.bak" "$SYNC_DIR/profile.new"
  rmdir "$SYNC_DIR" 2>/dev/null || true
  echo "Deleted synced data in $SYNC_DIR"
elif [ -n "$SYNC_DIR" ]; then
  echo "Synced data left in $SYNC_DIR (run with --purge to delete it)"
fi

echo
echo "Done. Last step: open brave://extensions and remove \"Brave Dual-Boot Sync\"."
