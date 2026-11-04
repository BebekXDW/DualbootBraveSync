# Brave Cookie Sync

Brave (Chromium MV3) extension + Python native-messaging helper that keeps cookies in sync between an Arch Linux and a Windows install on the same dual-boot PC. Brave Sync covers tabs/extensions/passwords; this project only handles cookies, which Brave Sync can't.

## Layout

- `extension/` — MV3 extension, loaded unpacked in `brave://extensions`.
  - `background.js` — service worker: all sync logic.
  - `popup.html` / `popup.js` — status + Save now / Load now / Test buttons.
  - `manifest.json` — has a fixed `key`, so the extension ID is always `mdbmccmhobidhmobkaiogmiembhamgdf`. Don't remove the key: both installers hard-code that ID in `allowed_origins`.
- `host/cookie_sync_host.py` — native messaging host (host name `com.cookiesync.host`). Commands: `info`, `read` (chunked, offset/length), `save` (atomic write via `.tmp`, keeps `.bak`). Reads the sync file path from `config.json` next to itself.
- `install-linux.sh` — copies host to `~/.local/share/cookie-sync`, writes manifest to `~/.config/BraveSoftware/Brave-Browser/NativeMessagingHosts/` (override with `MANIFEST_DIR`).
- `install-windows.ps1` — copies host to `%LOCALAPPDATA%\CookieSync`, writes a `.bat` launcher + manifest, registers under HKCU Chrome and Brave `NativeMessagingHosts` keys.

## How sync works

- The shared file (`cookies.json` on an NTFS partition both OSes mount) holds `{version, savedAt, machine, cookies[]}`.
- `chrome.storage.local.lastSync` = `savedAt` of the last file this profile wrote or loaded.
- On startup / install / new window: if file `savedAt > lastSync`, load it (set changed cookies, remove ones missing from the file, reload http(s) tabs).
- On `cookies.onChanged`: debounce 2 s, then save. Also save when the last window closes, plus a 1-min alarm if dirty.
- Before saving, if the file is newer than `lastSync`, load instead of overwriting (protects the other OS's data).
- `quietUntil` suppresses the `onChanged` storm caused by our own import so it doesn't immediately re-save.
- Native replies are capped at 1 MB by Chromium, hence the chunked `read`.

## Testing

Tested end-to-end in headless Chromium via Playwright with two profiles standing in for the two OSes (login carried over; logout + changed cookie carried back). **Not yet tested** in real Brave, on Windows, or with a real NTFS share. Things worth checking there:

- Windows PowerShell 5.1 `Set-Content -Encoding UTF8` writes a BOM. The host reads `config.json` with `utf-8-sig` to cope; confirm Brave accepts the BOM'd native-messaging manifest JSON (if not, write it without BOM).
- Brave on Windows may only read the Chrome registry key, the Brave key, or both — installer writes both.
- Whether `windows.onRemoved` save completes before Brave fully exits.

Quick manual host test (Linux):

```
printf '%s' '{"cmd":"info"}' | python3 -c "import sys,struct;d=sys.stdin.buffer.read();sys.stdout.buffer.write(struct.pack('@I',len(d))+d)" | ~/.local/share/cookie-sync/cookie_sync_host.py | tail -c +5
```

## Security

The sync file is plaintext live session cookies. Never commit it, never put it in a cloud-synced folder. `.gitignore` excludes `cookies.json*` and `config.json`.
