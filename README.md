# Brave Dual-Boot Sync (Arch ⇄ Windows)

Makes Brave on Arch and Brave on Windows feel like the same browser, with no Brave Sync account. Close Brave on one system, reboot, open it on the other, and it continues where you left off.

| What | How it moves |
|---|---|
| Logins (cookies) | Live, by the extension, a couple of seconds after every change |
| Open windows & tabs, tab groups, pinned tabs | By the launcher when Brave closes / opens |
| Bookmarks, history, top sites, address-bar suggestions | Launcher |
| Settings: appearance, theme & dark mode, toolbar, bookmarks bar, new-tab page layout & widgets, Shields & per-site settings, languages, spellcheck, brave://flags, privacy toggles | Launcher |
| Custom new-tab background images | Launcher |
| Extensions | The popup lists ones installed on the other system with one-click store links (Brave doesn't let an extension install others) |

**Not synced, on purpose:**
- **Passwords and payment cards.** Use Bitwarden.
- **Brave Wallet, Rewards and VPN data.** These hold keys and credentials.
- **A few settings Brave locks with tamper protection:** startup pages ("Continue where you left off"), homepage, default search engine and the installed-extensions list. Set these once on each system. Turn on **Settings → Get started → "Continue where you left off"** on both systems, or your tabs won't reopen.

## How it works

- **The extension** saves cookies to `cookies.json` in the shared folder while you browse and loads the other system's newer copy when Brave starts.
- **The launcher** (`profile_sync.py launch`) handles everything else. Brave rewrites its profile files while it runs, so the launcher works around a session: it loads the other system's newer snapshot, starts Brave, waits for Brave to close, then saves a new snapshot to `profile/` in the shared folder. It also runs once at login.
- The newest side always wins. If the shared snapshot is newer than anything this system has loaded, the launcher refuses to overwrite it.
- Before every load, the previous local files are backed up to the helper's `backup/` folder (one older generation is kept in `backup.old/`).

## 1. Pick a shared location

Windows can't read Arch's ext4 partition, so the folder has to live on an **NTFS** partition that both systems can see, such as a separate data drive like `D:`.

On Arch, mount it at a fixed place on every boot. Find its UUID with `lsblk -f` and add a line to `/etc/fstab`:

```
UUID=XXXXXXXXXXXXXXXX  /mnt/shared  ntfs3  uid=1000,gid=1000,rw,noatime,nofail  0 0
```

Then run `sudo mkdir -p /mnt/shared && sudo mount -a` (check your user ID with `id -u`).

**Turn off Windows Fast Startup**: Control Panel → Power Options → "Choose what the power buttons do" → untick "Turn on fast startup". Otherwise Windows leaves the drive locked and Arch can only mount it read-only.

Same folder, two names:
- Windows: `D:\brave-sync`
- Arch: `/mnt/shared/brave-sync`

## 2. Install on Arch

```
./install-linux.sh /mnt/shared/brave-sync
```

Needs `python` and the native Brave package (`brave-bin`). The Flatpak can't start outside programs. The installer makes your normal Brave menu entry go through the launcher, adds `~/.local/bin/brave-sync`, and enables a small login service.

## 3. Install on Windows

Install Python 3 from python.org (tick "Add to PATH"). Then, in PowerShell inside this folder:

```
powershell -ExecutionPolicy Bypass -File .\install-windows.ps1 -SyncDir D:\brave-sync
```

This creates a **Brave (Sync)** shortcut on the desktop and in the Start menu. **Always start Brave from that shortcut**: unpin the old Brave icon and pin this one. A login item loads newer data when you sign in.

## 4. Load the extension (on both systems)

1. Open `brave://extensions` and turn on **Developer mode**
2. **Load unpacked** → pick the `extension` folder (keep it somewhere permanent)
3. Open the popup and press **Test**. It should say "Helper OK".

## 5. First sync

Start on the system that has the profile you want to keep. Open Brave through the launcher, then close it. That saves the first snapshot. Reboot into the other system and open Brave through its launcher, and everything comes across.

## Good to know

- **Close Brave before you reboot.** If the system shuts down while Brave is open, the launcher tries to wait for Brave to close and save. On Windows, shutdown usually kills it first, so that session's tabs and settings won't carry over (logins still do, live).
- If you open Brave without the launcher, for example from a link in another app on Windows, that session isn't snapshotted. The next launcher start notices and won't overwrite newer data from the other system.
- **The shared folder holds your live logins and browsing history.** Keep it on your own disk, never in a cloud folder.
- Some sites (Google, banks, Discord) tie a session to a device and may still ask you to sign in again.
- Check the state any time: `python3 ~/.local/share/cookie-sync/profile_sync.py status` (Windows: `py %LOCALAPPDATA%\CookieSync\profile_sync.py status`). The log is `sync.log` in the same folder.
- To undo a bad load, close Brave and copy the files from `backup/` back into your Brave profile folder.

## License

[PolyForm Noncommercial 1.0.0](LICENSE): free to use, modify and share for non-commercial purposes. Commercial use requires permission.
