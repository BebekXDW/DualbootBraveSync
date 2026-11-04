# Cookie Sync for Brave (Arch ⇄ Windows dual boot)

While Brave is open, this extension saves your cookies to a shared file. It saves a couple of seconds after any change, and again when Brave closes. When Brave starts on the other OS, the extension sees that the file is newer and loads it. Logins, and logouts, carry over with no clicking.

Use Brave Sync (Menu → Sync) for tabs, extensions, passwords and settings. This extension only handles cookies.

## 1. Pick a shared location

Windows can't read Arch's ext4 partition, so the file has to live on an **NTFS** partition that both systems can see. A separate data drive like `D:` is ideal.

On Arch, mount that partition at a fixed place on every boot. Find its UUID with `lsblk -f`, then add a line to `/etc/fstab`:

```
UUID=XXXXXXXXXXXXXXXX  /mnt/shared  ntfs3  uid=1000,gid=1000,rw,noatime,nofail  0 0
```

Then run `sudo mkdir -p /mnt/shared && sudo mount -a`. If your user ID isn't 1000, check it with `id -u`.

**Turn off Windows Fast Startup.** Control Panel → Power Options → "Choose what the power buttons do" → untick "Turn on fast startup". Otherwise Windows leaves the drive locked, and Arch can only mount it read-only.

Example paths for the same file:
- Windows: `D:\cookie-sync\cookies.json`
- Arch: `/mnt/shared/cookie-sync/cookies.json`

## 2. Install on Arch

```
./install-linux.sh /mnt/shared/cookie-sync/cookies.json
```

Needs `python` (`sudo pacman -S python`). If you use Brave from Flatpak, the browser can't start outside programs, so use the AUR or official build (`brave-bin`).

## 3. Install on Windows

Install Python 3 from python.org and tick "Add to PATH". Then, in PowerShell inside this folder, run:

```
powershell -ExecutionPolicy Bypass -File .\install-windows.ps1 -SyncFile D:\cookie-sync\cookies.json
```

## 4. Load the extension (on both systems)

1. Open `brave://extensions`
2. Turn on **Developer mode** (top right)
3. Click **Load unpacked** and pick the `extension` folder
4. Pin it, open the popup, and press **Test**. It should say "Helper OK".

The extension has a fixed ID (`mdbmccmhobidhmobkaiogmiembhamgdf`) so the same helper setup works on both systems. Keep the `extension` folder somewhere permanent, because Brave loads it from there.

Start on the OS where you're currently logged in to everything. Browse for a moment (or press **Save now**), then reboot into the other OS and open Brave.

## Good to know

- **The cookies file contains your live logins.** Anyone who copies it can get into your accounts. Keep it on your own disk, not in a cloud folder. A `cookies.json.bak` with the previous version sits next to it.
- On Windows, turn off Settings → System → "Continue running background apps when Brave is closed". Otherwise Brave never really quits. The extension also checks for a newer file whenever a window opens, so this is a backup measure.
- Some sites (Google, banks, Discord) tie a session to a device and may still ask you to sign in again.
- If the shared drive isn't mounted, saving stops with an error in the popup instead of writing somewhere else.
- The last ~2 seconds of changes before a sudden crash or power cut can be lost.

## License

[PolyForm Noncommercial 1.0.0](LICENSE): free to use, modify and share for non-commercial purposes. Commercial use requires permission.
