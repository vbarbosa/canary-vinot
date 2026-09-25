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


if __name__ == "__main__":
    main()
