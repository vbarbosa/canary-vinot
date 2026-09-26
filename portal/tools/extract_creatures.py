"""Cut creature sprites (standing, facing south) from the Tibia 13.40 client assets into
app/static/creatures/<slug>.png, enlarged with nearest-neighbour so they stay crisp.

    python tools/extract_creatures.py

The server's data/items/appearances.dat says which sprites each outfit (looktype) uses; the
client's catalog-content.json and sprite sheets hold the pixels. Only the sheets needed are
downloaded from the same assets tag the game client is built from.
"""

import io
import json
import lzma
import os
import sys
import urllib.request

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..", "..")
OUT = os.path.join(HERE, "..", "app", "static", "creatures")
RAW = "https://raw.githubusercontent.com/dudantas/tibia-client/13.40.93b0a1/assets/"
SPRITE_SIZES = {0: (32, 32), 1: (32, 64), 2: (64, 32), 3: (64, 64)}
SCALE = 3

# slug: (name shown on the site, looktype from data-otservbr-global/monster)
CREATURES = {
    "rat": ("Rat", 21),
    "wolf": ("Wolf", 27),
    "troll": ("Troll", 15),
    "bear": ("Bear", 16),
    "minotaur": ("Minotaur", 25),
    "giant-spider": ("Giant Spider", 38),
    "cyclops": ("Cyclops", 22),
    "vampire": ("Vampire", 68),
    "dragon": ("Dragon", 34),
    "dragon-lord": ("Dragon Lord", 39),
    "hydra": ("Hydra", 121),
    "behemoth": ("Behemoth", 55),
    "demon": ("Demon", 35),
    "orshabaal": ("Orshabaal", 201),
}


def _varint(buf, pos):
    result = shift = 0
    while True:
        b = buf[pos]
        pos += 1
        result |= (b & 0x7F) << shift
        if not b & 0x80:
            return result, pos
        shift += 7


def _fields(buf):
    pos = 0
    while pos < len(buf):
        key, pos = _varint(buf, pos)
        num, wt = key >> 3, key & 7
        if wt == 0:
            val, pos = _varint(buf, pos)
        elif wt == 2:
            ln, pos = _varint(buf, pos)
            val = buf[pos:pos + ln]
            pos += ln
        elif wt == 1:
            val, pos = buf[pos:pos + 8], pos + 8
        elif wt == 5:
            val, pos = buf[pos:pos + 4], pos + 4
        else:
            raise ValueError(f"wire type {wt}")
        yield num, wt, val


def _packed(wt, val):
    if wt == 0:
        return [val]
    out, pos = [], 0
    while pos < len(val):
        v, pos = _varint(val, pos)
        out.append(v)
    return out


def outfit_sprites(path, wanted):
    """{looktype: (layers, [sprite ids])} of the first frame group.
    Appearances.outfit = 2; Appearance.id = 1, .frame_group = 2; FrameGroup.sprite_info = 3;
    SpriteInfo.layers = 4, .sprite_id = 5."""
    out = {}
    for num, wt, obj in _fields(open(path, "rb").read()):
        if num != 2 or wt != 2:
            continue
        oid, info = None, None
        for n, w, v in _fields(obj):
            if n == 1 and w == 0:
                oid = v
            elif n == 2 and w == 2 and info is None:
                for fn, fw, fv in _fields(v):
                    if fn == 3 and fw == 2:
                        layers, ids = 1, []
                        for sn, sw, sv in _fields(fv):
                            if sn == 4:
                                layers = sv
                            elif sn == 5:
                                ids += _packed(sw, sv)
                        info = (layers, ids)
        if oid in wanted and info:
            out[oid] = info
    return out


def fetch(name):
    with urllib.request.urlopen(RAW + name, timeout=120) as r:
        return r.read()


def decode_sheet(data):
    """CIP sheet: zero padding, 5 constant bytes, 7-bit size, LZMA props, 8 size bytes, raw LZMA1 -> BMP."""
    pos = 0
    while data[pos] == 0:
        pos += 1
    pos += 5
    while data[pos] & 0x80:
        pos += 1
    pos += 1
    props = data[pos:pos + 5]
    pos += 5 + 8
    d = props[0]
    filt = {"id": lzma.FILTER_LZMA1, "lc": d % 9, "lp": (d // 9) % 5, "pb": d // 45,
            "dict_size": int.from_bytes(props[1:5], "little")}
    bmp = lzma.LZMADecompressor(format=lzma.FORMAT_RAW, filters=[filt]).decompress(data[pos:])
    img = Image.open(io.BytesIO(bmp)).convert("RGBA")
    px = list(img.get_flattened_data()) if hasattr(img, "get_flattened_data") else list(img.getdata())
    if not any(a < 255 for *_, a in px):
        img.putdata([(r, g, b, 0) if (r, g, b) == (255, 0, 255) else (r, g, b, a) for r, g, b, a in px])
    return img


def main():
    looktypes = {lt for _, lt in CREATURES.values()}
    sprites = outfit_sprites(os.path.join(ROOT, "data", "items", "appearances.dat"), looktypes)
    catalog = json.loads(fetch("catalog-content.json"))
    sheets = [e for e in catalog if e.get("type") == "sprite"]
    cache = {}
    os.makedirs(OUT, exist_ok=True)
    meta = {}
    for slug, (name, lt) in CREATURES.items():
        if lt not in sprites:
            print("no outfit", lt, name, file=sys.stderr)
            continue
        layers, ids = sprites[lt]
        # sprite order is (frame, z, y, direction, layer); direction 2 = south, layer 0 = the body
        sid = ids[min(2 * layers, len(ids) - 1)]
        entry = next(e for e in sheets if e["firstspriteid"] <= sid <= e["lastspriteid"])
        if entry["file"] not in cache:
            cache[entry["file"]] = decode_sheet(fetch(entry["file"]))
        sheet = cache[entry["file"]]
        w, h = SPRITE_SIZES.get(entry.get("spritetype", 0), (32, 32))
        idx = sid - entry["firstspriteid"]
        cols = sheet.width // w
        img = sheet.crop(((idx % cols) * w, (idx // cols) * h, (idx % cols) * w + w, (idx // cols) * h + h))
        img = img.crop(img.getbbox() or (0, 0, w, h))
        img.resize((img.width * SCALE, img.height * SCALE), Image.NEAREST).save(os.path.join(OUT, f"{slug}.png"), optimize=True)
        meta[slug] = name
        print("ok", name, img.size)
    with open(os.path.join(OUT, "creatures.json"), "w") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)


if __name__ == "__main__" and "--vocations" not in sys.argv:
    main()


# ------------------------------------------------------------- player outfits (vocation art)

def outfit_color(c):
    """Tibia's 133-colour outfit palette (HSI), as in OTClient Outfit::getColor."""
    import colorsys
    if c >= 19 * 7:
        c = 0
    if c % 19 == 0:
        h, s, v = 0.0, 0.0, 1 - c / 19 / 7
    else:
        h = (c % 19) / 18
        s, v = {0: (0.25, 1.0), 1: (0.25, 0.75), 2: (0.5, 0.75), 3: (0.667, 0.75), 4: (1.0, 1.0), 5: (1.0, 0.75), 6: (1.0, 0.5)}[c // 19]
    r, g, b = colorsys.hsv_to_rgb(h, s, v)
    return int(r * 255), int(g * 255), int(b * 255)


def nearest_color(rgb):
    return min(range(133), key=lambda i: sum((a - b) ** 2 for a, b in zip(outfit_color(i), rgb)))


def outfit_infos(path, wanted):
    """{looktype: dict(px, py, pz, layers, ids)} of the first frame group."""
    out = {}
    for num, wt, obj in _fields(open(path, "rb").read()):
        if num != 2 or wt != 2:
            continue
        oid, info = None, None
        for n, w, v in _fields(obj):
            if n == 1 and w == 0:
                oid = v
            elif n == 2 and w == 2 and info is None:
                for fn, fw, fv in _fields(v):
                    if fn == 3 and fw == 2:
                        info = {"px": 1, "py": 1, "pz": 1, "layers": 1, "ids": []}
                        for sn, sw, sv in _fields(fv):
                            key = {1: "px", 2: "py", 3: "pz", 4: "layers"}.get(sn)
                            if key:
                                info[key] = sv
                            elif sn == 5:
                                info["ids"] += _packed(sw, sv)
        if oid in wanted and info:
            out[oid] = info
    return out


class Sprites:
    def __init__(self):
        self.catalog = [e for e in json.loads(fetch("catalog-content.json")) if e.get("type") == "sprite"]
        self.cache = {}

    def get(self, sid):
        entry = next(e for e in self.catalog if e["firstspriteid"] <= sid <= e["lastspriteid"])
        if entry["file"] not in self.cache:
            self.cache[entry["file"]] = decode_sheet(fetch(entry["file"]))
        sheet = self.cache[entry["file"]]
        w, h = SPRITE_SIZES.get(entry.get("spritetype", 0), (32, 32))
        idx = sid - entry["firstspriteid"]
        cols = sheet.width // w
        return sheet.crop(((idx % cols) * w, (idx // cols) * h, (idx % cols) * w + w, (idx // cols) * h + h))


def colorize(base, mask, colors):
    """Tint the base sprite where the template mask is yellow/red/green/blue (head/body/legs/feet)."""
    out = base.copy()
    bp, mp, op = base.load(), mask.load(), out.load()
    keys = {(255, 255, 0): "head", (255, 0, 0): "body", (0, 255, 0): "legs", (0, 0, 255): "feet"}
    for y in range(base.height):
        for x in range(base.width):
            r, g, b, a = mp[x, y]
            part = keys.get((r, g, b)) if a else None
            if part:
                cr, cg, cb = colors[part]
                br, bg, bb, ba = bp[x, y]
                op[x, y] = (br * cr // 255, bg * cg // 255, bb * cb // 255, ba)
    return out


def render_outfit(sprites, info, colors, addons=(1, 2), direction=2):
    layers = info["layers"]

    def sprite(x, y, layer):
        i = ((y * info["px"]) + x) * layers + layer
        return sprites.get(info["ids"][i]) if i < len(info["ids"]) else None

    img = None
    for y in (0,) + tuple(a for a in addons if a < info["py"]):
        base = sprite(direction, y, 0)
        if base is None:
            continue
        if layers > 1:
            mask = sprite(direction, y, 1)
            if mask is not None:
                base = colorize(base, mask, colors)
        img = base if img is None else Image.alpha_composite(img, base)
    return img


# VinOT colours for the vocation heroes (nearest entries of Tibia's outfit palette)
VOCATION_OUTFITS = {
    "knight": (131, {"head": (240, 200, 90), "body": (170, 40, 30), "legs": (70, 70, 80), "feet": (110, 70, 40)}),
    "paladin": (129, {"head": (120, 80, 40), "body": (60, 130, 50), "legs": (120, 80, 40), "feet": (80, 50, 30)}),
    "sorcerer": (130, {"head": (140, 80, 200), "body": (110, 60, 180), "legs": (240, 200, 90), "feet": (60, 40, 90)}),
    "druid": (144, {"head": (90, 160, 60), "body": (60, 120, 50), "legs": (160, 120, 60), "feet": (90, 60, 30)}),
}


def vocations(scale=4):
    infos = outfit_infos(os.path.join(ROOT, "data", "items", "appearances.dat"), {lt for lt, _ in VOCATION_OUTFITS.values()})
    sprites = Sprites()
    out_dir = os.path.join(HERE, "..", "app", "static", "heroes")
    os.makedirs(out_dir, exist_ok=True)
    for voc, (lt, target) in VOCATION_OUTFITS.items():
        colors = {part: outfit_color(nearest_color(rgb)) for part, rgb in target.items()}
        img = render_outfit(sprites, infos[lt], colors)
        img = img.crop(img.getbbox())
        img.resize((img.width * scale, img.height * scale), Image.NEAREST).save(os.path.join(out_dir, f"{voc}.png"), optimize=True)
        print("ok", voc, img.size, infos[lt]["px"], infos[lt]["py"], infos[lt]["layers"])


if __name__ == "__main__" and "--vocations" in sys.argv:
    vocations()
