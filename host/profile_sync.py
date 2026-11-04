#!/usr/bin/env python3
"""Profile sync for Brave (dual boot).

Copies bookmarks, history, open tabs and windows, settings, site/Shields
settings, appearance and new-tab backgrounds between the two systems through
the shared folder. Brave rewrites these files while it runs, so they are only
touched while Brave is closed:

  launch [args]   load the other system's newer snapshot, start Brave, wait
                  for it to close, then save a snapshot (the shortcut runs this)
  import          load the newer snapshot now (also runs at login)
  export          save a snapshot now
  status          show what the shared folder and this system hold
  --force         with import/export: skip the "who is newer" check

Left out on purpose: passwords, payment data, Brave Wallet / Rewards / VPN
data, and the few settings Brave guards with tamper protection (startup
pages, homepage, default search engine, installed extensions). Those are
set once on each system.
"""
import copy
import glob
import json
import logging
import logging.handlers
import os
import platform
import re
import shutil
import signal
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(HERE, "config.json")
STATE = os.path.join(HERE, "state.json")
BACKUP = os.path.join(HERE, "backup")
WIN = os.name == "nt"
SNAP = "profile"

# Profile items copied as-is (all are portable between Windows and Linux).
FILES = ["Bookmarks", "History", "Favicons", "Top Sites", "Shortcuts",
         "Visited Links", "Custom Dictionary.txt"]
DIRS = ["Sessions"]  # open windows, tabs, tab groups, pinned tabs
BACKGROUND_GLOB = "*background*"  # custom new-tab background images
SQLITE_SIDE = ("-journal", "-wal", "-shm")


def paths(*dotted):
    return {tuple(p.split(".")) for p in dotted}


# Preferences that are machine-specific, account/credential related, or
# telemetry. Everything else in Preferences is synced.
SKIP_PREFS = paths(
    "protection", "extensions", "download", "savefile", "selectfile",
    "sync", "gcm", "account_info", "signin", "google", "gaia_cookie",
    "invalidation", "web_apps", "media", "optimization_guide", "net",
    "updateclientdata", "variations", "segmentation_platform",
    "profile.exit_type", "profile.exited_cleanly", "profile.created_by_version",
    "browser.window_placement", "browser.app_window_placement",
    "brave.sync", "brave.wallet", "brave.rewards", "brave.brave_ads",
    "brave.stats", "brave.p3a", "brave.vpn", "brave.skus",
)
# Local State is browser-wide (brave://flags, dark mode, ...). It also holds
# the key that encrypts passwords and cookies, which is never copied.
SKIP_LOCAL_STATE = paths(
    "os_crypt", "profile", "user_experience_metrics", "variations",
    "uninstall_metrics", "stability", "updateclientdata", "breadcrumbs",
    "tab_stats", "was", "legacy", "network_time", "invalidation",
    "optimization_guide", "component_updater", "subresource_filter",
    "hardware_acceleration_mode_previous", "background_mode",
    "brave.stats", "brave.p3a", "brave.referral", "brave.wallet",
    "brave.vpn", "brave.skus", "brave.rewards",
)
SENSITIVE = ("password", "credential", "token", "secret", "keyring",
             "wallet", "encrypted", "private_key")
PATHLIKE = re.compile(r"^(?:[A-Za-z]:[\\/]|\\\\|/(?:home|root|usr|opt|mnt|media|run|tmp|var)/)")
DROP = object()

log = logging.getLogger("profile-sync")


class SyncError(Exception):
    pass


# ---------- small helpers ----------

def setup_log():
    h = logging.handlers.RotatingFileHandler(
        os.path.join(HERE, "sync.log"), maxBytes=200_000, backupCount=1, encoding="utf-8")
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    log.addHandler(h)
    if sys.stderr is not None:
        log.addHandler(logging.StreamHandler())
    log.setLevel(logging.INFO)


def read_json(path, default=None):
    try:
        with open(path, encoding="utf-8-sig") as f:
            return json.load(f)
    except FileNotFoundError:
        return default


def write_json(path, data, compact=False):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        if compact:
            json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
        else:
            json.dump(data, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def copy_item(src, dst):
    if os.path.isdir(src):
        shutil.rmtree(dst, ignore_errors=True)
        shutil.copytree(src, dst)
    else:
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)


def default_user_data_dir():
    if WIN:
        return os.path.join(os.environ["LOCALAPPDATA"], "BraveSoftware", "Brave-Browser", "User Data")
    return os.path.expanduser("~/.config/BraveSoftware/Brave-Browser")


def load_config():
    cfg = read_json(CONFIG)
    if cfg is None:
        raise SyncError(f"Missing {CONFIG}; run the installer")
    if "sync_dir" not in cfg and "sync_file" in cfg:  # older installs
        cfg["sync_dir"] = os.path.dirname(cfg["sync_file"])
    cfg["sync_dir"] = os.path.abspath(os.path.expanduser(cfg["sync_dir"]))
    cfg["user_data_dir"] = os.path.abspath(os.path.expanduser(
        cfg.get("user_data_dir") or default_user_data_dir()))
    cfg["profile_dir"] = os.path.join(cfg["user_data_dir"], cfg.get("profile") or "Default")
    cfg["snap_dir"] = os.path.join(cfg["sync_dir"], SNAP)
    return cfg


def find_brave(cfg):
    if cfg.get("brave"):
        return cfg["brave"]
    if WIN:
        for base in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)"),
                     os.environ.get("LOCALAPPDATA")):
            if base:
                p = os.path.join(base, "BraveSoftware", "Brave-Browser", "Application", "brave.exe")
                if os.path.isfile(p):
                    return p
    else:
        for name in ("brave", "brave-browser", "brave-browser-stable"):
            p = shutil.which(name)
            if p:
                return p
    raise SyncError('Brave not found; set "brave" in config.json')


def brave_running(cfg):
    if WIN:
        r = subprocess.run(["tasklist", "/FI", "IMAGENAME eq brave.exe", "/NH"],
                           capture_output=True, text=True,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return "brave.exe" in r.stdout.lower()
    # Chromium keeps a SingletonLock symlink ("hostname-pid") while running.
    try:
        target = os.readlink(os.path.join(cfg["user_data_dir"], "SingletonLock"))
    except OSError:
        return False
    try:
        os.kill(int(target.rsplit("-", 1)[1]), 0)
        return True
    except ProcessLookupError:
        return False  # left over from a crash
    except (ValueError, IndexError, PermissionError):
        return True


def get_state():
    return read_json(STATE, {}) or {}


def set_state(**kw):
    s = get_state()
    s.update(kw)
    write_json(STATE, s)


def report(message, error=False):
    (log.error if error else log.info)(message)
    set_state(message=message, error=error, at=int(time.time() * 1000))
    if error and not WIN and shutil.which("notify-send"):
        subprocess.run(["notify-send", "Brave profile sync", message], check=False)


# ---------- preference filtering ----------

def protected(*docs):
    """Pref paths Brave guards with tamper protection (listed in protection.macs)."""
    out = set()

    def walk(node, path):
        if isinstance(node, dict):
            for k, v in node.items():
                walk(v, path + (k,))
        else:
            out.add(path)

    for d in docs:
        walk(((d or {}).get("protection") or {}).get("macs") or {}, ())
    return out


def filtered(node, skip, path=()):
    if path in skip:
        return DROP
    if path and any(w in path[-1].lower() for w in SENSITIVE):
        return DROP
    if isinstance(node, dict):
        out = {}
        for k, v in node.items():
            r = filtered(v, skip, path + (k,))
            if r is not DROP:
                out[k] = r
        return out
    if isinstance(node, str) and PATHLIKE.match(node):
        return DROP  # a file path from one OS means nothing on the other
    return node


def merge(dst, src):
    for k, v in src.items():
        if isinstance(v, dict) and isinstance(dst.get(k), dict):
            merge(dst[k], v)
        else:
            dst[k] = copy.deepcopy(v)
    return dst


def extension_list(profile_dir):
    found = {}
    for name in ("Secure Preferences", "Preferences"):
        doc = read_json(os.path.join(profile_dir, name), {}) or {}
        settings = (doc.get("extensions") or {}).get("settings") or {}
        for ext_id, s in settings.items():
            if not isinstance(s, dict) or s.get("location") in (5, 10):
                continue  # built into Brave
            m = s.get("manifest") or {}
            found.setdefault(ext_id, {
                "id": ext_id,
                "name": m.get("name") or ext_id,
                "store": s.get("location") == 1 or bool(s.get("from_webstore")),
                "unpacked": s.get("location") == 4,
            })
    return sorted(found.values(), key=lambda e: e["name"].lower())


def profile_items(profile_dir):
    names = {n for n in FILES + DIRS if os.path.exists(os.path.join(profile_dir, n))}
    names |= {os.path.basename(p) for p in glob.glob(os.path.join(glob.escape(profile_dir), BACKGROUND_GLOB))}
    return sorted(names)


# ---------- export / import ----------

def snapshot_manifest(cfg):
    return read_json(os.path.join(cfg["snap_dir"], "manifest.json"))


def export(cfg, force=False):
    prof, snap = cfg["profile_dir"], cfg["snap_dir"]
    if brave_running(cfg):
        raise SyncError("Brave is still running")
    if not os.path.isdir(cfg["sync_dir"]):
        raise SyncError(f"Shared folder not found: {cfg['sync_dir']} (is the drive mounted?)")
    if not os.path.isfile(os.path.join(prof, "Preferences")):
        raise SyncError(f"No Brave profile at {prof}")
    man = snapshot_manifest(cfg)
    if man and man.get("savedAt", 0) > get_state().get("synced", 0) and not force:
        raise SyncError(f"The shared snapshot from {man.get('machine')} is newer and was never "
                        "loaded here; not overwriting it (run import, or export --force)")

    tmp = snap + ".new"
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(os.path.join(tmp, "files"))
    items = profile_items(prof)
    for n in items:
        copy_item(os.path.join(prof, n), os.path.join(tmp, "files", n))

    prefs = read_json(os.path.join(prof, "Preferences"), {})
    secure = read_json(os.path.join(prof, "Secure Preferences"), {})
    write_json(os.path.join(tmp, "prefs.json"), filtered(prefs, SKIP_PREFS | protected(prefs, secure)))
    ls = read_json(os.path.join(cfg["user_data_dir"], "Local State"), {})
    write_json(os.path.join(tmp, "local_state.json"), filtered(ls, SKIP_LOCAL_STATE | protected(ls)))
    write_json(os.path.join(tmp, "extensions.json"), extension_list(prof))

    saved = int(time.time() * 1000)
    write_json(os.path.join(tmp, "manifest.json"),
               {"version": 1, "savedAt": saved, "machine": platform.system(), "files": items})
    if os.path.exists(snap):
        shutil.rmtree(snap + ".bak", ignore_errors=True)
        os.replace(snap, snap + ".bak")
    os.replace(tmp, snap)
    set_state(synced=saved)
    return f"Saved bookmarks, tabs and settings ({len(items)} items)"


def backup_local(cfg):
    prof = cfg["profile_dir"]
    shutil.rmtree(BACKUP + ".old", ignore_errors=True)
    if os.path.exists(BACKUP):
        os.replace(BACKUP, BACKUP + ".old")
    os.makedirs(BACKUP)
    for n in profile_items(prof) + ["Preferences"]:
        if os.path.exists(os.path.join(prof, n)):
            copy_item(os.path.join(prof, n), os.path.join(BACKUP, n))
    ls = os.path.join(cfg["user_data_dir"], "Local State")
    if os.path.exists(ls):
        copy_item(ls, os.path.join(BACKUP, "Local State"))


def import_(cfg, force=False):
    prof, snap = cfg["profile_dir"], cfg["snap_dir"]
    man = snapshot_manifest(cfg)
    if not man:
        return "No shared snapshot yet; one is saved when Brave closes"
    if man.get("savedAt", 0) <= get_state().get("synced", 0) and not force:
        return "Up to date"
    if brave_running(cfg):
        raise SyncError("Close Brave first")

    os.makedirs(prof, exist_ok=True)
    backup_local(cfg)
    for n in man.get("files", []):
        src = os.path.join(snap, "files", n)
        if not os.path.exists(src):
            continue
        dst = os.path.join(prof, n)
        for side in SQLITE_SIDE:  # stale journals would not match the new database
            if os.path.exists(dst + side):
                os.remove(dst + side)
        copy_item(src, dst)

    pp = os.path.join(prof, "Preferences")
    prefs = read_json(pp, {})
    secure = read_json(os.path.join(prof, "Secure Preferences"), {})
    incoming = read_json(os.path.join(snap, "prefs.json"), {})
    merge(prefs, filtered(incoming, SKIP_PREFS | protected(prefs, secure)))
    write_json(pp, prefs, compact=True)

    lsp = os.path.join(cfg["user_data_dir"], "Local State")
    ls = read_json(lsp, {})
    merge(ls, filtered(read_json(os.path.join(snap, "local_state.json"), {}),
                       SKIP_LOCAL_STATE | protected(ls)))
    if WIN:
        # Keep Brave from lingering in the background after its windows close,
        # so the snapshot gets saved.
        ls.setdefault("background_mode", {})["enabled"] = False
    write_json(lsp, ls, compact=True)

    set_state(synced=man["savedAt"])
    return f"Loaded bookmarks, tabs and settings from {man.get('machine', 'the other system')}"


# ---------- commands ----------

def launch(cfg, args):
    brave = find_brave(cfg)
    if brave_running(cfg):
        subprocess.Popen([brave] + args)  # just opens a window in the running Brave
        return
    try:
        report(import_(cfg))
    except Exception as e:  # never stop Brave from opening
        report(f"Loading failed: {e}", error=True)

    stopping = []
    for sig in (signal.SIGTERM, getattr(signal, "SIGHUP", None)):
        if sig is not None:
            signal.signal(sig, lambda *_: stopping.append(True))

    proc = subprocess.Popen([brave] + args)
    while proc.poll() is None:
        time.sleep(1)
    waited = 0
    while brave_running(cfg):  # Brave can outlive the process we started
        if stopping and waited > 30:
            report("System shut down before Brave finished closing; not saved", error=True)
            return
        time.sleep(2)
        waited += 2
    try:
        report(export(cfg))
    except Exception as e:
        report(f"Saving failed: {e}", error=True)


def show_status(cfg):
    man = snapshot_manifest(cfg)
    st = get_state()
    print(f"Shared folder: {cfg['sync_dir']}")
    print(f"Profile:       {cfg['profile_dir']}")
    print(f"Brave running: {brave_running(cfg)}")
    if man:
        when = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(man["savedAt"] / 1000))
        newer = man["savedAt"] > st.get("synced", 0)
        print(f"Snapshot:      saved {when} on {man.get('machine')}"
              + ("  (newer, will load on next start)" if newer else "  (in sync)"))
    else:
        print("Snapshot:      none yet")
    if st.get("message"):
        print(f"Last result:   {st['message']}")


def main():
    setup_log()
    argv = sys.argv[1:]
    if not argv or argv[0] not in ("launch", "import", "export", "status"):
        print(__doc__)
        return 2
    cmd, rest = argv[0], argv[1:]
    force = cmd != "launch" and "--force" in rest
    try:
        cfg = load_config()
        if cmd == "launch":
            launch(cfg, rest)
        elif cmd == "import":
            report(import_(cfg, force))
        elif cmd == "export":
            report(export(cfg, force))
        else:
            show_status(cfg)
    except SyncError as e:
        report(str(e), error=True)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
