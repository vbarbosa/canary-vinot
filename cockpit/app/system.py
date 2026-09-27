"""Host metrics read from /proc (the container sees the VM's numbers) and read-only log browsing."""

import os
import shutil
import socket
import time

# name=path pairs; only files directly inside these folders can be opened
LOG_DIRS = dict(
    part.split("=", 1)
    for part in os.environ.get("COCKPIT_LOG_DIRS", "Servidor=/srv/canary/logs,Comandos GM=/srv/canary/data/logs").split(",")
    if "=" in part
)
SERVICES = [
    ("Jogo", os.environ.get("COCKPIT_GAME_HOST", "server"), int(os.environ.get("COCKPIT_GAME_PORT", "7172"))),
    ("Login", os.environ.get("COCKPIT_LOGIN_HOST", "login"), int(os.environ.get("COCKPIT_LOGIN_PORT", "8080"))),
]
MAX_LINES = 2000

_last_cpu = {}


def _cpu_percent(key):
    """CPU use since the previous call with the same key (the page and the recorder keep separate windows)."""
    with open("/proc/stat") as f:
        vals = [int(v) for v in f.readline().split()[1:]]
    idle, total = vals[3] + vals[4], sum(vals)
    prev, _last_cpu[key] = _last_cpu.get(key), (idle, total)
    if not prev:
        time.sleep(0.2)
        return _cpu_percent(key)
    d_total = total - prev[1]
    return round(100 * (1 - (idle - prev[0]) / d_total), 1) if d_total else 0.0


def host(key="page"):
    info = {}
    try:
        mem = {}
        with open("/proc/meminfo") as f:
            for line in f:
                k, v = line.split(":", 1)
                mem[k] = int(v.split()[0]) * 1024
        info["mem_total"] = mem["MemTotal"]
        info["mem_used"] = mem["MemTotal"] - mem.get("MemAvailable", mem["MemFree"])
        with open("/proc/loadavg") as f:
            info["load"] = f.read().split()[:3]
        with open("/proc/uptime") as f:
            info["uptime"] = int(float(f.read().split()[0]))
        info["cpus"] = os.cpu_count()
        info["cpu"] = _cpu_percent(key)
    except OSError:
        pass
    disk = shutil.disk_usage(next((d for d in LOG_DIRS.values() if os.path.isdir(d)), "/"))
    info["disk_total"], info["disk_used"] = disk.total, disk.used
    return info


def services():
    out = []
    for name, host_, port in SERVICES:
        t = time.time()
        try:
            with socket.create_connection((host_, port), timeout=1.5):
                out.append({"name": name, "ok": True, "ms": int((time.time() - t) * 1000), "where": f"{host_}:{port}"})
        except OSError:
            out.append({"name": name, "ok": False, "ms": None, "where": f"{host_}:{port}"})
    return out


def log_files():
    out = []
    for label, path in LOG_DIRS.items():
        files = []
        if os.path.isdir(path):
            for e in os.scandir(path):
                if e.is_file():
                    st = e.stat()
                    files.append({"name": e.name, "size": st.st_size, "mtime": int(st.st_mtime), "active": is_active(st.st_mtime)})
        files.sort(key=lambda f: f["mtime"], reverse=True)
        out.append({"label": label, "exists": os.path.isdir(path), "files": files[:200]})
    return out


def is_active(mtime):
    """A log written in the last 10 minutes is still being written; older ones are history."""
    return time.time() - mtime < 600


def log_path(label, name):
    """Absolute path of a log file, or None if it is not a plain file inside a known log folder."""
    base = LOG_DIRS.get(label)
    if not base or "/" in name or name in (".", ".."):
        return None
    path = os.path.realpath(os.path.join(base, name))
    if os.path.dirname(path) != os.path.realpath(base) or not os.path.isfile(path):
        return None
    return path


def tail(path, lines=500, grep=""):
    lines = max(10, min(lines, MAX_LINES))
    with open(path, "rb") as f:
        f.seek(0, os.SEEK_END)
        size = f.tell()
        chunk = min(size, 4 * 1024 * 1024)
        f.seek(size - chunk)
        text = f.read().decode("utf-8", errors="replace")
    rows = text.splitlines()
    if grep:
        g = grep.lower()
        rows = [r for r in rows if g in r.lower()]
    return rows[-lines:]


def level(line):
    low = line.lower()
    if "error" in low or "fatal" in low or "segmentation" in low or "exception" in low:
        return "err"
    if "warn" in low:
        return "warn"
    return ""


def human_bytes(n):
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024


def human_duration(s):
    d, s = divmod(int(s), 86400)
    h, s = divmod(s, 3600)
    m = s // 60
    return (f"{d}d " if d else "") + f"{h}h {m}min"
