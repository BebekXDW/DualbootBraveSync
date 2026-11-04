#!/usr/bin/env python3
"""Native helper for the Cookie Sync extension.

Brave starts this program when the extension needs to read or write the
shared cookies file. It talks over stdin/stdout using Chrome's native
messaging format (4-byte length + JSON). The file location comes from
config.json next to this script.
"""
import json
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(HERE, "config.json")


def read_message():
    raw_len = sys.stdin.buffer.read(4)
    if len(raw_len) < 4:
        return None
    (length,) = struct.unpack("@I", raw_len)
    return json.loads(sys.stdin.buffer.read(length).decode("utf-8"))


def send(obj):
    data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    sys.stdout.buffer.write(struct.pack("@I", len(data)))
    sys.stdout.buffer.write(data)
    sys.stdout.buffer.flush()


def sync_file():
    with open(CONFIG, encoding="utf-8-sig") as f:
        path = json.load(f)["sync_file"]
    return os.path.abspath(os.path.expanduser(path))


def handle(msg):
    path = sync_file()
    cmd = msg.get("cmd")

    if cmd == "info":
        if not os.path.isfile(path):
            return {"ok": True, "path": path, "exists": False, "savedAt": 0}
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return {"ok": True, "path": path, "exists": True,
                "savedAt": data.get("savedAt", 0), "size": os.path.getsize(path)}

    if cmd == "read":
        with open(path, encoding="utf-8") as f:
            text = f.read()
        offset = int(msg.get("offset", 0))
        length = int(msg.get("length", 250000))
        return {"ok": True, "chunk": text[offset:offset + length], "total": len(text)}

    if cmd == "save":
        folder = os.path.dirname(path)
        if not os.path.isdir(folder):
            # Most likely the shared drive isn't mounted. Don't create a
            # stray folder in its place.
            return {"ok": False, "error": f"Folder not found: {folder} (is the shared drive mounted?)"}
        payload = msg["payload"]
        json.loads(payload)  # make sure it's valid before touching the file
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
        if os.path.exists(path):
            os.replace(path, path + ".bak")
        os.replace(tmp, path)
        return {"ok": True}

    return {"ok": False, "error": f"Unknown command: {cmd}"}


def main():
    msg = read_message()
    if msg is None:
        return
    try:
        send(handle(msg))
    except Exception as e:  # report every failure back to the extension
        send({"ok": False, "error": f"{type(e).__name__}: {e}"})


if __name__ == "__main__":
    main()
