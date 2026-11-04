#!/usr/bin/env bash
# Installs the Cookie Sync helper for Brave on Linux.
# Usage: ./install-linux.sh /path/to/shared/drive/cookie-sync/cookies.json
set -euo pipefail

EXT_ID="mdbmccmhobidhmobkaiogmiembhamgdf"
HOST_NAME="com.cookiesync.host"
SRC="$(cd "$(dirname "$0")" && pwd)"
DEST="$HOME/.local/share/cookie-sync"
MANIFEST_DIR="${MANIFEST_DIR:-$HOME/.config/BraveSoftware/Brave-Browser/NativeMessagingHosts}"

SYNC_FILE="${1:-}"
if [ -z "$SYNC_FILE" ]; then
  read -rp "Full path of the shared cookies file (on a drive Windows can see too): " SYNC_FILE
fi
SYNC_FILE="${SYNC_FILE/#\~/$HOME}"

command -v python3 >/dev/null || { echo "python3 is required (sudo pacman -S python)"; exit 1; }

mkdir -p "$DEST" "$MANIFEST_DIR"
cp "$SRC/host/cookie_sync_host.py" "$DEST/"
chmod +x "$DEST/cookie_sync_host.py"

python3 - "$DEST/config.json" "$SYNC_FILE" <<'EOF'
import json, sys
json.dump({"sync_file": sys.argv[2]}, open(sys.argv[1], "w"), indent=2)
EOF

cat > "$MANIFEST_DIR/$HOST_NAME.json" <<EOF
{
  "name": "$HOST_NAME",
  "description": "Cookie Sync helper",
  "path": "$DEST/cookie_sync_host.py",
  "type": "stdio",
  "allowed_origins": ["chrome-extension://$EXT_ID/"]
}
EOF

mkdir -p "$(dirname "$SYNC_FILE")" 2>/dev/null || true
echo "Done."
echo "  Helper:   $DEST"
echo "  Manifest: $MANIFEST_DIR/$HOST_NAME.json"
echo "  Sync file: $SYNC_FILE"
[ -d "$(dirname "$SYNC_FILE")" ] || echo "  WARNING: $(dirname "$SYNC_FILE") doesn't exist yet. Mount the shared drive first."
