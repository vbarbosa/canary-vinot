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

KINDS = {"meu": "⭐ Salvos", "cidade": "🏛 Cidades", "viagem": "⛵ Viagens", "hunt": "⚔ Hunts", "npc": "🧙 NPCs", "casa": "🏠 Casas"}

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

    # hunting spots: for each monster, the 32x32 area (per floor) where most of them spawn
    buckets = defaultdict(lambda: defaultdict(lambda: [0, 0, 0, Counter()]))  # name -> area -> [count, sum x, sum y, neighbours]
    totals = Counter()
    try:
        for _, spawn in ET.iterparse(os.path.join(world, "otservbr-monster.xml")):
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
                totals[name] += n
            spawn.clear()
    except (OSError, ET.ParseError):
        pass
    for name, areas in buckets.items():
        (_, _, z), (n, sx, sy, near) = max(areas.items(), key=lambda kv: kv[1][0])
        others = ", ".join(m for m, _ in near.most_common(4) if m != name)
        out.append(_place("hunt", name, sx // n, sy // n, z, f"{totals[name]} no mapa · {n} aqui" + (f" com {others}" if others else "")))

    try:
        for h in ET.parse(os.path.join(world, "otservbr-house.xml")).getroot():
            out.append(_place("casa", h.get("name"), h.get("entryx"), h.get("entryy"), h.get("entryz"),
                              "guildhall" if h.get("guildhall") == "true" else "casa"))
    except (OSError, ET.ParseError):
        pass
    return out


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
