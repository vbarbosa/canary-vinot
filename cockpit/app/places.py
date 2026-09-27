"""Places to teleport to: temples, travel stops, NPCs, hunting spots, houses and places saved by hand.

Everything except the saved places is read once from the datapack (world/*.xml and npc/*.lua).
Map thumbnails are cut from the public TibiaMaps floor images, which match the OTServBR global map.
"""

import glob
import io
import os
import re
import threading
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from functools import lru_cache

from . import db

DATAPACK = os.environ.get("COCKPIT_DATAPACK_DIR", os.path.join(os.path.dirname(os.environ.get("COCKPIT_DATA_DIR", "/srv/canary/data")), "data-otservbr-global"))
MAP_DIR = os.environ.get("COCKPIT_MAP_DIR", os.path.join(os.environ.get("COCKPIT_ICON_DIR", "/srv/cockpit/icons"), "map"))
MAP_URL = "https://raw.githubusercontent.com/tibiamaps/tibia-map-data/main/data/floor-{:02d}-map.png"
MAP_X, MAP_Y, MAP_W, MAP_H = 31744, 30976, 2560, 2048

KINDS = {"meu": "⭐ Salvos", "criatura": "🐉 Criaturas", "cidade": "🏛 Cidades", "viagem": "⛵ Viagens", "hunt": "⚔ Hunts", "npc": "🧙 NPCs", "casa": "🏠 Casas"}

JOIN = 40  # spawn squares whose centres are this close (in sqm, same floor) count as one hunting spot

TRAVEL_RE = re.compile(
    r'addTravelKeyword\(\s*"([^"]+)"\s*,\s*\d+\s*,\s*(?:\{\s*x\s*=\s*(\d+)\s*,\s*y\s*=\s*(\d+)\s*,\s*z\s*=\s*(\d+)\s*\}|Position\((\d+),\s*(\d+),\s*(\d+)\))'
)


def _place(kind, name, x, y, z, detail=""):
    return {"kind": kind, "name": name, "x": int(x), "y": int(y), "z": int(z), "detail": detail}


@lru_cache(maxsize=1)
def world_places():
    out = []
    # boat, carpet and other travel stops: keep the most common destination for each name
    stops = defaultdict(Counter)
    for path in glob.glob(os.path.join(DATAPACK, "npc", "*.lua")):
        with open(path, encoding="utf-8", errors="replace") as f:
            for m in TRAVEL_RE.finditer(f.read()):
                coords = m.group(2, 3, 4) if m.group(2) else m.group(5, 6, 7)
                stops[m.group(1).strip().title()][tuple(int(c) for c in coords)] += 1
    for name, counts in stops.items():
        out.append(_place("viagem", name, *counts.most_common(1)[0][0], "parada de barco, tapete ou viagem"))

    world = os.path.join(DATAPACK, "world")
    try:
        for spawn in ET.parse(os.path.join(world, "otservbr-npc.xml")).getroot():
            for npc in spawn:
                out.append(_place("npc", npc.get("name"), spawn.get("centerx"), spawn.get("centery"), spawn.get("centerz"), "NPC"))
    except (OSError, ET.ParseError):
        pass

    # hunting spots: for each monster, the area where most of them spawn
    for name, areas in spawns().items():
        a = areas[0]
        others = ", ".join(a["near"][:3])
        out.append(_place("hunt", name, a["x"], a["y"], a["z"],
                          f"{sum(r['n'] for r in areas)} no mapa · {a['n']} aqui" + (f" com {others}" if others else "")))

    try:
        for h in ET.parse(os.path.join(world, "otservbr-house.xml")).getroot():
            out.append(_place("casa", h.get("name"), h.get("entryx"), h.get("entryy"), h.get("entryz"),
                              "guildhall" if h.get("guildhall") == "true" else "casa"))
    except (OSError, ET.ParseError):
        pass
    return out


@lru_cache(maxsize=1)
def spawns():
    """Every monster's spawn areas (32x32 squares per floor), busiest first: name -> [{x, y, z, n, near}]."""
    buckets = defaultdict(lambda: defaultdict(lambda: [0, 0, 0, Counter()]))  # name -> area -> [count, sum x, sum y, neighbours]
    try:
        for _, spawn in ET.iterparse(os.path.join(DATAPACK, "world", "otservbr-monster.xml")):
            if spawn.tag != "monster" or spawn.get("centerx") is None:
                continue
            x, y, z = int(spawn.get("centerx")), int(spawn.get("centery")), int(spawn.get("centerz"))
            counts = Counter(m.get("name") for m in spawn)
            for name, n in counts.items():
                b = buckets[name][(x // 32, y // 32, z)]
                b[0] += n
                b[1] += x * n
                b[2] += y * n
                b[3].update(counts)
            spawn.clear()
    except (OSError, ET.ParseError):
        pass
    out = {}
    for name, areas in buckets.items():
        # join squares that touch into one hunting spot, growing from the busiest square
        clusters = []
        for (_, _, z), (n, sx, sy, near) in sorted(areas.items(), key=lambda kv: -kv[1][0]):
            x, y = sx / n, sy / n
            c = next((c for c in clusters if c["z"] == z and abs(c["sx"] / c["n"] - x) <= JOIN and abs(c["sy"] / c["n"] - y) <= JOIN), None)
            if c is None:
                clusters.append({"z": z, "n": n, "sx": sx, "sy": sy, "near": Counter(near)})
            else:
                c["n"] += n
                c["sx"] += sx
                c["sy"] += sy
                c["near"].update(near)
        rows = [{"x": c["sx"] // c["n"], "y": c["sy"] // c["n"], "z": c["z"], "n": c["n"],
                 "near": [m for m, _ in c["near"].most_common(5) if m != name][:4]} for c in clusters]
        out[name] = sorted(rows, key=lambda r: -r["n"])
    return out


def creatures(q="", limit=60):
    """Monsters whose name matches, most common first: [{name, total, areas, x, y, z}] and the grand total."""
    q = q.strip().lower()
    rows = [{"name": name, "total": sum(a["n"] for a in areas), "areas": len(areas), **{k: areas[0][k] for k in "xyz"}}
            for name, areas in spawns().items() if not q or q in name.lower()]
    rows.sort(key=lambda r: (bool(q) and not r["name"].lower().startswith(q), -r["total"], r["name"]))
    return rows[:limit], len(rows)


def creature(name):
    """(canonical name, spawn areas) for one monster, matching the name case-insensitively."""
    for n, areas in spawns().items():
        if n.lower() == name.strip().lower():
            return n, areas
    return None, []


def landmarks():
    """Town temples, to say roughly where a spot is."""
    return [(t["name"], t["posx"], t["posy"]) for t in db.all("SELECT name, posx, posy FROM towns")]


def nearest(x, y, marks):
    return min(marks, key=lambda m: (m[1] - x) ** 2 + (m[2] - y) ** 2)[0] if marks else ""


def all_places():
    saved = [dict(_place("meu", r["name"], r["x"], r["y"], r["z"], r["note"]), id=r["id"])
             for r in db.all("SELECT * FROM cockpit_places ORDER BY name")]
    towns = [_place("cidade", t["name"], t["posx"], t["posy"], t["posz"], "templo") for t in db.all("SELECT * FROM towns ORDER BY name")]
    return saved + towns + world_places()


def search(q="", kind="", limit=60):
    q = q.strip().lower()
    rows = [p for p in all_places() if (not kind or p["kind"] == kind) and (not q or q in p["name"].lower() or q in p["detail"].lower())]
    if q:  # names that start with the query first
        rows.sort(key=lambda p: (not p["name"].lower().startswith(q), p["name"].lower()))
    return rows[:limit], len(rows)


# ---------------------------------------------------------------- map thumbnails

_lock = threading.Lock()


def _floor(z):
    path = os.path.join(MAP_DIR, f"floor-{z:02d}.png")
    with _lock:
        if not os.path.exists(path):
            os.makedirs(MAP_DIR, exist_ok=True)
            with urllib.request.urlopen(MAP_URL.format(z), timeout=30) as r, open(path + ".tmp", "wb") as f:
                f.write(r.read())
            os.replace(path + ".tmp", path)
    return path


@lru_cache(maxsize=16)
def _floor_image(z):
    from PIL import Image

    return Image.open(_floor(z)).convert("RGB")


def thumbnail(x, y, z, radius=40, scale=3):
    """PNG bytes of the map around (x, y, z) with a marker in the middle, or None when it is off the known map."""
    px, py = x - MAP_X, y - MAP_Y
    if not (0 <= z <= 15 and 0 <= px < MAP_W and 0 <= py < MAP_H):
        return None
    try:
        from PIL import Image, ImageDraw

        img = _floor_image(z).crop((px - radius, py - radius, px + radius, py + radius))
    except Exception:
        return None
    img = img.resize((img.width * scale, img.height * scale), Image.NEAREST)
    d = ImageDraw.Draw(img)
    c, r = radius * scale + scale // 2, 7
    d.ellipse((c - r, c - r, c + r, c + r), outline=(255, 255, 255), width=3)
    d.ellipse((c - r + 2, c - r + 2, c + r - 2, c + r - 2), outline=(220, 40, 40), width=2)
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    return buf.getvalue()
