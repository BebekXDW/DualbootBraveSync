#!/usr/bin/env bash
# Installs Brave Dual-Boot Sync on Linux.
# Usage: ./install-linux.sh /mnt/shared/brave-sync
#   (a folder on a drive Windows can see too; Windows must use the same folder)
set -euo pipefail

EXT_ID="mdbmccmhobidhmobkaiogmiembhamgdf"
HOST_NAME="com.cookiesync.host"
SRC="$(cd "$(dirname "$0")" && pwd)"
DEST="$HOME/.local/share/cookie-sync"
UDD="${BRAVE_USER_DATA:-$HOME/.config/BraveSoftware/Brave-Browser}"
MANIFEST_DIR="${MANIFEST_DIR:-$UDD/NativeMessagingHosts}"
LAUNCHER="$HOME/.local/bin/brave-sync"

SYNC_DIR="${1:-}"
if [ -z "$SYNC_DIR" ]; then
  read -rp "Shared folder for Brave sync (on a drive Windows can see too): " SYNC_DIR
fi
SYNC_DIR="${SYNC_DIR/#\~/$HOME}"
case "$SYNC_DIR" in *.json) SYNC_DIR="$(dirname "$SYNC_DIR")" ;; esac  # old-style file path

command -v python3 >/dev/null || { echo "python3 is required (sudo pacman -S python)"; exit 1; }

BRAVE=""
for n in brave brave-browser brave-browser-stable; do
  if p="$(command -v "$n")"; then BRAVE="$p"; break; fi
done
[ -n "$BRAVE" ] || echo "WARNING: Brave not found on PATH. Set \"brave\" in $DEST/config.json."

mkdir -p "$DEST" "$MANIFEST_DIR" "$(dirname "$LAUNCHER")"
cp "$SRC/host/cookie_sync_host.py" "$SRC/host/profile_sync.py" "$DEST/"
chmod +x "$DEST/cookie_sync_host.py" "$DEST/profile_sync.py"

python3 - "$DEST/config.json" "$SYNC_DIR" "$UDD" "$BRAVE" <<'EOF'
import json, sys
cfg = {"sync_dir": sys.argv[2], "user_data_dir": sys.argv[3], "profile": "Default"}
if sys.argv[4]:
    cfg["brave"] = sys.argv[4]
json.dump(cfg, open(sys.argv[1], "w"), indent=2)
EOF

cat > "$MANIFEST_DIR/$HOST_NAME.json" <<EOF
{
  "name": "$HOST_NAME",
  "description": "Brave Dual-Boot Sync helper",
  "path": "$DEST/cookie_sync_host.py",
  "type": "stdio",
  "allowed_origins": ["chrome-extension://$EXT_ID/"]
}
EOF

# Launcher: syncs the profile around each Brave session.
cat > "$LAUNCHER" <<EOF
#!/bin/sh
exec python3 "$DEST/profile_sync.py" launch "\$@"
EOF
chmod +x "$LAUNCHER"

# Make the normal Brave menu entry (and links opened from other apps) go
# through the launcher. A copy in ~/.local/share/applications overrides
# the system one without touching it.
APPS="$HOME/.local/share/applications"
mkdir -p "$APPS"
OVERRIDDEN=""
for f in /usr/share/applications/brave-browser.desktop /usr/share/applications/brave.desktop; do
  [ -f "$f" ] || continue
  sed -E "s#^Exec=[^ ]+#Exec=$LAUNCHER#" "$f" > "$APPS/$(basename "$f")"
  OVERRIDDEN="$OVERRIDDEN $APPS/$(basename "$f")"
done
command -v update-desktop-database >/dev/null && update-desktop-database "$APPS" 2>/dev/null || true

# At login, load a newer snapshot before anything can start Brave.
UNIT_DIR="$HOME/.config/systemd/user"
mkdir -p "$UNIT_DIR"
cat > "$UNIT_DIR/brave-profile-import.service" <<EOF
[Unit]
Description=Load the newer Brave profile snapshot from the shared drive

[Service]
Type=oneshot
ExecStart=/usr/bin/env python3 $DEST/profile_sync.py import

[Install]
WantedBy=default.target
EOF
if command -v systemctl >/dev/null && systemctl --user daemon-reload 2>/dev/null; then
  systemctl --user enable brave-profile-import.service >/dev/null 2>&1 || true
else
  echo "  NOTE: couldn't enable the login service (no systemd user session)."
fi

mkdir -p "$SYNC_DIR" 2>/dev/null || true
echo "Done."
echo "  Helper:      $DEST"
echo "  Launcher:    $LAUNCHER"
echo "  Menu entry:  ${OVERRIDDEN:-none found, start Brave with $LAUNCHER}"
echo "  Shared dir:  $SYNC_DIR"
[ -d "$SYNC_DIR" ] || echo "  WARNING: $SYNC_DIR doesn't exist. Mount the shared drive first."
