"""Client releases for the Download page.

Each release is a folder in PORTAL_DOWNLOADS (a read-only volume), named after its version:

    /downloads/1.2.0/VinOT-Setup-1.2.0.exe
    /downloads/1.2.0/VinOT-1.2.0.apk
    /downloads/1.2.0/NOTAS.md      optional: first line is the title, "- " lines are the changes

The newest folder is the current release; the others show up as older versions.
"""

import datetime as dt
import hashlib
import os
import re
import threading

ROOT = os.environ.get("PORTAL_DOWNLOADS", "/downloads")
PLATFORMS = {
    "windows": {"exts": (".exe", ".msi", ".zip"), "label": "Windows"},
    "android": {"exts": (".apk",), "label": "Android"},
}
VERSION_RE = re.compile(r"^[0-9A-Za-z][0-9A-Za-z._-]{0,31}$")
_sha = {}
_lock = threading.Lock()


def _version_key(name):
    return [int(p) if p.isdigit() else p for p in re.split(r"[._-]", name)]


def sha256(path):
    st = os.stat(path)
    key = (path, st.st_mtime, st.st_size)
    with _lock:
        if key in _sha:
            return _sha[key]
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    with _lock:
        _sha[key] = h.hexdigest()
    return _sha[key]


def _notes(folder):
    for name in ("NOTAS.md", "NOTES.md", "notas.md"):
        path = os.path.join(folder, name)
        if os.path.isfile(path):
            lines = [l.rstrip() for l in open(path, encoding="utf-8", errors="replace").read().splitlines() if l.strip()]
            title = lines[0].lstrip("# ").strip() if lines and not lines[0].startswith("-") else ""
            items = [l.lstrip("-* ").strip() for l in lines if l.lstrip().startswith(("-", "*"))]
            return title, items
    return "", []


def releases():
    """Newest first: [{version, date, title, notes, files: {platform: {...}}}]."""
    try:
        names = [n for n in os.listdir(ROOT) if VERSION_RE.match(n) and os.path.isdir(os.path.join(ROOT, n))]
    except OSError:
        return []
    out = []
    for version in names:
        folder = os.path.join(ROOT, version)
        files = {}
        for fname in sorted(os.listdir(folder)):
            path = os.path.join(folder, fname)
            if fname.startswith(".") or not os.path.isfile(path):
                continue
            for plat, spec in PLATFORMS.items():
                if fname.lower().endswith(spec["exts"]) and plat not in files:
                    st = os.stat(path)
                    files[plat] = {"name": fname, "path": path, "size": st.st_size, "mtime": st.st_mtime,
                                   "url": f"/baixar/{version}/{fname}", "label": spec["label"]}
        if not files:
            continue
        title, notes = _notes(folder)
        newest = max(f["mtime"] for f in files.values())
        out.append({"version": version, "date": dt.datetime.fromtimestamp(newest, dt.timezone.utc).isoformat(),
                    "title": title, "notes": notes, "files": files})
    out.sort(key=lambda r: (_version_key(r["version"]), r["date"]), reverse=True)
    return out


def latest_file(platform):
    for r in releases():
        if platform in r["files"]:
            return r["files"][platform]
    return None


def find(version, fname):
    """The file path, only if it is a real release file (no path tricks)."""
    if not VERSION_RE.match(version) or "/" in fname or "\\" in fname or fname.startswith("."):
        return None
    for r in releases():
        if r["version"] == version:
            for f in r["files"].values():
                if f["name"] == fname:
                    return f["path"]
    return None


def human_size(n):
    return f"{n / 1048576:.1f} MB".replace(".", ",") if n >= 1048576 else f"{n / 1024:.0f} KB"
