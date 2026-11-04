#!/usr/bin/env python3
"""End-to-end test of profile_sync.py and the native host, using two fake
Brave profiles ("A" and "B") standing in for the two systems. No Brave needed
(Linux only: the fake Brave uses a SingletonLock symlink).

    python3 tests/test_profile_sync.py
"""
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import textwrap

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
T = tempfile.mkdtemp(prefix="brave-sync-test-")
SHARED = os.path.join(T, "shared")
failures = []


def check(cond, what):
    print(("  ok   " if cond else "  FAIL ") + what)
    if not cond:
        failures.append(what)


def write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(data if isinstance(data, str) else json.dumps(data))


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def rjson(path):
    return json.loads(read(path))


def make_system(name, prefs, secure, local_state, files):
    base = os.path.join(T, name)
    helper = os.path.join(base, "helper")
    udd = os.path.join(base, "udd")
    prof = os.path.join(udd, "Default")
    os.makedirs(helper)
    for f in ("profile_sync.py", "cookie_sync_host.py"):
        shutil.copy(os.path.join(ROOT, "host", f), helper)
    fake = os.path.join(base, "fake-brave")
    write(fake, textwrap.dedent(f"""\
        #!/bin/sh
        ln -sf "host-$$" "{udd}/SingletonLock"
        sleep 1
        echo '{{"edited": "on {name}"}}' > "{prof}/Bookmarks"
        rm -f "{udd}/SingletonLock"
        """))
    os.chmod(fake, 0o755)
    write(os.path.join(helper, "config.json"),
          {"sync_dir": SHARED, "user_data_dir": udd, "profile": "Default", "brave": fake})
    write(os.path.join(prof, "Preferences"), prefs)
    write(os.path.join(prof, "Secure Preferences"), secure)
    write(os.path.join(udd, "Local State"), local_state)
    for rel, content in files.items():
        write(os.path.join(prof, rel), content)
    return {"helper": helper, "udd": udd, "prof": prof}


def run(sysd, *args):
    r = subprocess.run([sys.executable, os.path.join(sysd["helper"], "profile_sync.py"), *args],
                       capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def host(sysd, msg):
    data = json.dumps(msg).encode()
    r = subprocess.run([sys.executable, os.path.join(sysd["helper"], "cookie_sync_host.py")],
                       input=struct.pack("@I", len(data)) + data, capture_output=True)
    return json.loads(r.stdout[4:])


os.makedirs(SHARED)
A = make_system(
    "A",
    prefs={
        "homepage": "https://a-home.example",
        "protection": {"macs": {"homepage": "MAC"}},
        "bookmark_bar": {"show_on_all_tabs": True},
        "brave": {"new_tab_page": {"show_clock": True}, "wallet": {"keyrings": "SECRET"}},
        "profile": {"exit_type": "Crashed",
                    "content_settings": {"exceptions": {"cookies": {"https://a.com:443,*": {"setting": 2}}}}},
        "download": {"default_directory": "/home/a/Downloads"},
        "misc": {"auth_token": "TOKEN", "last_dir": "/home/a/Pictures", "label": "kept"},
        "spellcheck": {"dictionaries": ["pl", "en-US"]},
    },
    secure={"extensions": {"settings": {
        "aaaa": {"location": 1, "manifest": {"name": "uBlock Origin"}},
        "bbbb": {"location": 5, "manifest": {"name": "Built-in"}},
    }}},
    local_state={"os_crypt": {"encrypted_key": "KEY-A"},
                 "browser": {"enabled_labs_experiments": ["flag-x@1"]},
                 "brave": {"dark_mode": 2}},
    files={"Bookmarks": '{"from": "A"}', "History": "HISTORY-A",
           "Sessions/Session_1": "TABS-A", "sanitized_background.jpg": "IMG-A"},
)
B = make_system(
    "B",
    prefs={"homepage": "https://b-home.example", "protection": {"macs": {"homepage": "MAC"}},
           "bookmark_bar": {"show_on_all_tabs": False}, "only_on_b": 1},
    secure={},
    local_state={"os_crypt": {"encrypted_key": "KEY-B"}},
    files={"Bookmarks": '{"from": "B-old"}', "History": "HISTORY-B", "History-journal": "STALE",
           "Sessions/Session_9": "OLD-TABS-B"},
)

print("1. Export on A")
rc, out = run(A, "export")
check(rc == 0, f"export succeeds ({out.strip()})")
snap = os.path.join(SHARED, "profile")
p = rjson(os.path.join(snap, "prefs.json"))
check("homepage" not in p, "tamper-protected pref (homepage) left out")
check("wallet" not in p.get("brave", {}), "Brave Wallet left out")
check("download" not in p, "download folder left out")
check("auth_token" not in p["misc"] and "last_dir" not in p["misc"] and p["misc"]["label"] == "kept",
      "token and file-path values left out, other values kept")
check("exit_type" not in p["profile"], "profile.exit_type left out")
check(p["profile"]["content_settings"]["exceptions"]["cookies"]["https://a.com:443,*"]["setting"] == 2,
      "site settings with dotted keys kept")
ls = rjson(os.path.join(snap, "local_state.json"))
check("os_crypt" not in ls and ls["brave"]["dark_mode"] == 2, "Local State: encryption key out, dark mode in")
ext = rjson(os.path.join(snap, "extensions.json"))
check([e["id"] for e in ext] == ["aaaa"], "extension list skips built-ins")
check(sorted(rjson(os.path.join(snap, "manifest.json"))["files"]) ==
      ["Bookmarks", "History", "Sessions", "sanitized_background.jpg"], "manifest lists copied items")

print("2. Import on B")
rc, out = run(B, "import")
check(rc == 0 and "Loaded" in out, f"import succeeds ({out.strip()})")
bp = rjson(os.path.join(B["prof"], "Preferences"))
check(bp["homepage"] == "https://b-home.example", "B keeps its own homepage")
check(bp["bookmark_bar"]["show_on_all_tabs"] is True, "setting from A applied")
check(bp["brave"]["new_tab_page"]["show_clock"] is True, "new-tab setting applied")
check(bp["only_on_b"] == 1 and bp["protection"]["macs"]["homepage"] == "MAC", "B-only prefs and MACs untouched")
bls = rjson(os.path.join(B["udd"], "Local State"))
check(bls["os_crypt"]["encrypted_key"] == "KEY-B", "B's encryption key untouched")
check(bls["browser"]["enabled_labs_experiments"] == ["flag-x@1"], "brave://flags applied")
check(read(os.path.join(B["prof"], "Bookmarks")) == '{"from": "A"}', "bookmarks copied")
check(read(os.path.join(B["prof"], "History")) == "HISTORY-A", "history copied")
check(not os.path.exists(os.path.join(B["prof"], "History-journal")), "stale SQLite journal removed")
check(os.listdir(os.path.join(B["prof"], "Sessions")) == ["Session_1"], "tabs/sessions replaced")
check(read(os.path.join(B["prof"], "sanitized_background.jpg")) == "IMG-A", "background image copied")
check(read(os.path.join(B["helper"], "backup", "Bookmarks")) == '{"from": "B-old"}', "B's old files backed up")
rc, out = run(B, "import")
check("Up to date" in out, "second import is a no-op")

print("3. Launch on B (fake Brave edits bookmarks), then A must not overwrite")
rc, out = run(B, "launch", "--new-window")
check(rc == 0 and "Saved" in out, f"launch exports after Brave closes ({out.strip().splitlines()[-1]})")
check("on B" in read(os.path.join(snap, "files", "Bookmarks")), "B's edit is in the snapshot")
rc, out = run(A, "export")
check(rc == 1 and "newer" in out, "A refuses to overwrite B's newer snapshot")
rc, out = run(A, "import")
check(rc == 0 and "on B" in read(os.path.join(A["prof"], "Bookmarks")), "A loads B's edit")

print("4. Running detection and native host")
os.symlink("host-999999999", os.path.join(A["udd"], "SingletonLock"))
rc, out = run(A, "status")
check("Brave running: False" in out, "stale SingletonLock is ignored")
os.remove(os.path.join(A["udd"], "SingletonLock"))
os.symlink(f"host-{os.getpid()}", os.path.join(A["udd"], "SingletonLock"))
rc, out = run(A, "import", "--force")
check(rc == 1 and "Close Brave" in out, "import refuses while Brave runs")
os.remove(os.path.join(A["udd"], "SingletonLock"))
r = host(A, {"cmd": "extensions"})
# The newest snapshot came from B, which has no extensions installed.
check(r["ok"] and r["extensions"] == rjson(os.path.join(snap, "extensions.json")) == [] and r["machine"],
      "host lists the snapshot's extensions")
r = host(A, {"cmd": "info"})
check(r["ok"] and r["path"].endswith("cookies.json") and "message" in r["profile"], "host info includes profile status")

shutil.rmtree(T)
print(f"\n{'ALL PASSED' if not failures else f'{len(failures)} FAILED'}")
sys.exit(1 if failures else 0)
