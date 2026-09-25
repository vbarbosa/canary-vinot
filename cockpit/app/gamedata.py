"""Static game data read once from the Canary datapack (items, outfits, mounts, vocations)."""

import os
import xml.etree.ElementTree as ET
from functools import lru_cache

DATA_DIR = os.environ.get("COCKPIT_DATA_DIR", os.path.join(os.path.dirname(__file__), "..", "..", "data"))

# primarytype values from items.xml grouped into the catalog filters
CATEGORIES = {
    "armas": {"sword weapons", "axe weapons", "club weapons", "distance weapons", "wands", "rods", "ammunition", "quivers"},
    "equipamento": {"helmets", "armors", "legs", "boots", "shields", "spellbooks", "amulets and necklaces", "rings", "clothing accessories"},
    "consumiveis": {"food", "liquids", "fluid containers", "attack runes", "support runes", "healing runes", "exercise weapons", "tools", "blessing charms"},
    "diversao": {"dolls and bears", "party items", "musical instruments", "trophies", "fansite items", "taming items", "magical items", "enchanted items", "contest prizes", "tournament rewards"},
    "decoracao": {"decoration", "furniture", "containers", "light sources", "flowers", "statues", "wall hangings", "tables", "closets", "casks", "illumination", "flags"},
    "valiosos": {"valuables", "creature products", "quest items", "metals", "keys"},
}

# map-building pieces that only clutter the gift catalog
HIDDEN_TYPES = {"natural tiles", "constructions", "walls", "artificial tiles", "rocks", "trees", "pillars", "windows", "fields", "grass", "stairs", "doors", "ladders", "bushes", "remains", "refuse", "rubbish", "blobs", "portals", "teleporters", "dropdowns", "skeletons", "floor decorations"}


def _attr(node, key):
    for a in node.findall("attribute"):
        if a.get("key", "").lower() == key:
            return a.get("value", "")
    return ""


@lru_cache(maxsize=1)
def items():
    """List of {id, name, type} for every named item, sorted by name."""
    out = []
    root = ET.parse(os.path.join(DATA_DIR, "items", "items.xml")).getroot()
    for node in root.iter("item"):
        name = node.get("name")
        if not name:
            continue
        ptype = _attr(node, "primarytype").lower()
        if ptype in HIDDEN_TYPES:
            continue
        ids = []
        if node.get("id"):
            ids = [int(node.get("id"))]
        elif node.get("fromid") and node.get("toid"):
            ids = range(int(node.get("fromid")), int(node.get("toid")) + 1)
        for i in ids:
            if i >= 100:
                out.append({"id": i, "name": name, "type": ptype})
    out.sort(key=lambda x: (x["name"].lower(), x["id"]))
    return out


def search_items(q="", cat="", limit=120):
    q = q.strip().lower()
    wanted = CATEGORIES.get(cat)
    res = []
    for it in items():
        if wanted and it["type"] not in wanted:
            continue
        if q and q not in it["name"] and q != str(it["id"]):
            continue
        res.append(it)
        if len(res) >= limit:
            break
    return res


@lru_cache(maxsize=1)
def item_names():
    return {it["id"]: it["name"] for it in items()}


@lru_cache(maxsize=1)
def outfits():
    """Outfits by sex: {0: [...], 1: [...]} with looktype and name."""
    res = {0: [], 1: []}
    root = ET.parse(os.path.join(DATA_DIR, "XML", "outfits.xml")).getroot()
    for o in root.iter("outfit"):
        if o.get("enabled", "yes") != "yes":
            continue
        res.setdefault(int(o.get("type")), []).append({"looktype": int(o.get("looktype")), "name": o.get("name")})
    return res


@lru_cache(maxsize=1)
def mounts():
    root = ET.parse(os.path.join(DATA_DIR, "XML", "mounts.xml")).getroot()
    return sorted(({"id": int(m.get("id")), "name": m.get("name")} for m in root.iter("mount")), key=lambda m: m["name"])


@lru_cache(maxsize=1)
def vocations():
    root = ET.parse(os.path.join(DATA_DIR, "XML", "vocations.xml")).getroot()
    return {int(v.get("id")): v.get("name") for v in root.iter("vocation")}


SKILLS = [
    (99, "Magic level", "maglevel"),
    (0, "Fist", "skill_fist"),
    (1, "Club", "skill_club"),
    (2, "Sword", "skill_sword"),
    (3, "Axe", "skill_axe"),
    (4, "Distance", "skill_dist"),
    (5, "Shielding", "skill_shielding"),
    (6, "Fishing", "skill_fishing"),
]

EFFECTS = [
    (30, "Fogos vermelhos"),
    (29, "Fogos amarelos"),
    (31, "Fogos azuis"),
    (36, "Coracoes"),
    (28, "Presente"),
    (13, "Brilho azul"),
    (5, "Explosao"),
    (50, "Luz sagrada"),
    (53, "Gelo gigante"),
]
