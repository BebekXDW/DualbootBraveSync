# Brave Dual-Boot Sync

Keeps Brave on an Arch Linux and a Windows install of the same dual-boot PC in sync, without Brave Sync. Two parts:

1. **Extension + native host**: live cookie sync (cookies are encrypted with a per-OS key on disk, so they can only move through the `chrome.cookies` API).
2. **Profile launcher** (`host/profile_sync.py`): copies profile files and merges settings while Brave is closed.

## Layout

- `extension/`: MV3 extension, loaded unpacked.
  - `background.js`: cookie sync logic, plus a `details` message for the popup (profile status from the host + extensions missing vs. the snapshot, via `chrome.management`).
  - `popup.html` / `popup.js`: cookie status and buttons, profile sync status, missing-extension store links.
  - `manifest.json`: fixed `key`, so the extension ID is always `mdbmccmhobidhmobkaiogmiembhamgdf`. Don't remove it: both installers hard-code that ID.
- `host/cookie_sync_host.py`: native messaging host `com.cookiesync.host`. Commands: `info` (also returns `profile` = launcher's `state.json`), `read` (chunked), `save` (atomic, keeps `.bak`), `extensions` (snapshot's `extensions.json`).
- `host/profile_sync.py`: `launch [brave args] | import | export | status`, `--force` for import/export. Stdlib only, runs on both OSes.
- `install-linux.sh`: installs to `~/.local/share/cookie-sync`, adds `~/.local/bin/brave-sync`, overrides the Brave `.desktop` in `~/.local/share/applications` (Exec → launcher), and a systemd user unit `brave-profile-import.service`.
- `install-windows.ps1`: installs to `%LOCALAPPDATA%\CookieSync`, registers the host (HKCU Chrome + Brave keys), and adds "Brave (Sync)" desktop and Start-menu shortcuts (pythonw) plus a Startup-folder import shortcut. Writes JSON without a BOM.

Both write `config.json`: `{sync_dir, user_data_dir, profile, brave}`. The host still accepts the old `{sync_file}`.

## Shared folder layout

```
<sync_dir>/cookies.json          extension (live)
<sync_dir>/profile/              launcher snapshot (profile.bak = previous, profile.new = in progress)
    manifest.json                {version, savedAt, machine, files[]}
    files/                       Bookmarks, History, Favicons, Top Sites, Shortcuts, Visited Links,
                                 Custom Dictionary.txt, Sessions/, *background*
    prefs.json                   filtered Preferences
    local_state.json             filtered Local State
    extensions.json              [{id, name, store, unpacked}]
```

## Rules the code relies on

- **Newest wins** via `savedAt` (ms). Per-OS `state.json.synced` = `savedAt` of the last snapshot this OS wrote or loaded. `import` only if snapshot > synced. `export` refuses if snapshot > synced (other OS data never loaded here) unless `--force`.
- **Files are only touched while Brave is closed** (`brave_running`: SingletonLock symlink + pid check on Linux, `tasklist` on Windows).
- **Prefs are deep-merged, never replaced.** Filtering drops: `SKIP_PREFS` / `SKIP_LOCAL_STATE` subtrees, every path listed in `protection.macs` of Preferences / Secure Preferences / Local State (tamper-protected prefs), keys containing sensitive words, and string values that look like absolute file paths.
- **Don't add MAC recomputation** or any other way around Brave's pref tamper protection. Protected settings (startup, homepage, search engine, extensions) are set by hand on each OS. Never sync `os_crypt`, `Login Data`, `Web Data`, `Cookies`, or Wallet/Rewards/VPN/SKU prefs.
- Import backs up the current local items to `backup/` (rotating to `backup.old/`) first, and deletes stale SQLite `-journal/-wal/-shm` beside replaced files.
- On Windows, import sets `background_mode.enabled=false` in Local State so Brave actually exits.

## Testing

- `python3 tests/test_profile_sync.py` runs export/import/launch and the native host against two fake profiles in a temp dir (Linux, stdlib only, no Brave needed). Run it after any change to `host/`.
- The cookie part was tested earlier in headless Chromium with two profiles.
- **Not yet tested with real Brave**, on Windows, or on a real NTFS share. Worth checking:
  - That Brave restores copied `Sessions/` from the other OS, and accepts the copied History/Favicons.
  - New-tab background file names (`*background*` glob is a guess at Brave's naming).
  - Brave on Windows reads the Chrome registry key, the Brave key, or both (installer writes both).
  - Whether `windows.onRemoved` cookie save finishes before Brave exits.

## Security

The shared folder contains live cookies and browsing history in plaintext. Never commit it, and never put it in a cloud-synced folder. `.gitignore` excludes `cookies.json*` and `config.json`.
