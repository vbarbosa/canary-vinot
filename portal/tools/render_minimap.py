"""Draw the minimap of the server's world map (.otbm), one PNG per floor, the way the game's automap
colours it, plus the towns (name and temple position) for the wiki.

    python tools/render_minimap.py WORLD.otbm OUT_DIR

Each tile takes the automap colour of its topmost item that has one (appearances.dat, flag 30).
OUT_DIR gets floor-NN.png, bounds.json ({"x0", "y0"} of the images) and towns.json.
"""

import json
import re
import os
import struct
import sys

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, HERE)

import extract_creatures as ec  # noqa: E402
from app import wiki  # noqa: E402

ESC, START, END = 0xFD, 0xFE, 0xFF
TILE_AREA, TILE, ITEM, TOWNS, TOWN, HOUSETILE = 4, 5, 6, 12, 13, 14
ATTR_TILE_FLAGS, ATTR_ITEM = 3, 9


def automap_colors():
    """{client item id: palette index} for every object with an automap colour."""
    out = {}
    buf = open(os.path.join(wiki.GAME, "data", "items", "appearances.dat"), "rb").read()
    for num, wt, obj in ec._fields(buf):
        if num != 1 or wt != 2:
            continue
        oid, color = None, None
        for n, w, v in ec._fields(obj):
            if n == 1 and w == 0:
                oid = v
            elif n == 3 and w == 2:
                for fn, fw, fv in ec._fields(v):
                    if fn == 30 and fw == 2:
                        for cn, cw, cv in ec._fields(fv):
                            if cn == 1 and cw == 0:
                                color = cv
        if oid is not None and color is not None:
            out[oid] = color
    return out


def palette():
    """Tibia's 6x6x6 automap palette as a flat list for a "P" image (index 255 = transparent/unknown)."""
    pal = []
    for i in range(256):
        if i < 216:
            pal += [(i // 36) * 51, ((i // 6) % 6) * 51, (i % 6) * 51]
        else:
            pal += [0, 0, 0]
    return pal


def nodes(data):
    """Yield (event, type, props) walking the node tree: ("start", type, props) and ("end", None, None).
    props is the unescaped bytes between the node type and its first child or its end."""
    i, n = 4, len(data)  # skip the 4-byte identifier
    special = re.compile(rb"[\xfd\xfe\xff]").search
    while i < n:
        b = data[i]
        if b == START:
            ntype = data[i + 1]
            i += 2
            # props run until the next unescaped START or END
            chunks, j = [], i
            while True:
                m = special(data, j)
                if not m:
                    return
                k = m.start()
                if data[k] == ESC:
                    chunks.append(data[j:k])
                    chunks.append(data[k + 1:k + 2])
                    j = k + 2
                    continue
                chunks.append(data[j:k])
                i = k
                break
            yield "start", ntype, b"".join(chunks)
        elif b == END:
            i += 1
            yield "end", None, None
        else:
            i += 1


def item_id(props):
    return struct.unpack_from("<H", props, 0)[0] if len(props) >= 2 else 0


def ground_id(props, offset):
    """The ground item stored as an attribute of the tile (OTBM_ATTR_ITEM)."""
    j = offset
    while j < len(props):
        attr = props[j]
        if attr == ATTR_TILE_FLAGS:
            j += 5
        elif attr == ATTR_ITEM:
            return struct.unpack_from("<H", props, j + 1)[0]
        else:
            return 0
    return 0


def main(world, out):
    os.makedirs(out, exist_ok=True)
    colors = automap_colors()
    data = open(world, "rb").read()
    tiles = {}  # z -> {(x, y): color}
    towns = []
    stack = []  # (type, base) for areas
    area = None
    tile = None  # [x, y, z, color]
    for ev, ntype, props in nodes(data):
        if ev == "end":
            t = stack.pop() if stack else None
            if t in (TILE, HOUSETILE) and tile and tile[3] is not None:
                tiles.setdefault(tile[2], {})[(tile[0], tile[1])] = tile[3]
                tile = None
            continue
        stack.append(ntype)
        if ntype == TILE_AREA:
            area = struct.unpack_from("<HHB", props, 0)
        elif ntype in (TILE, HOUSETILE) and area:
            x, y = area[0] + props[0], area[1] + props[1]
            gid = ground_id(props, 2 if ntype == TILE else 6)
            tile = [x, y, area[2], colors.get(gid)]
        elif ntype == ITEM and tile is not None and len(stack) >= 2 and stack[-2] in (TILE, HOUSETILE):
            c = colors.get(item_id(props))
            if c is not None:
                tile[3] = c
        elif ntype == TOWN:
            tid = struct.unpack_from("<I", props, 0)[0]
            ln = struct.unpack_from("<H", props, 4)[0]
            name = props[6:6 + ln].decode("latin-1")
            tx, ty, tz = struct.unpack_from("<HHB", props, 6 + ln)
            towns.append({"id": tid, "name": name, "x": tx, "y": ty, "z": tz})
    surface = tiles.get(7, {})
    # the main continent: around the towns' temples, which leaves out far-away test and event areas
    xs = [x for x, _ in surface] or [0]
    ys = [y for _, y in surface] or [0]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    main_towns = [t for t in towns if t["z"] == 7 and x0 <= t["x"] <= x1 and y0 <= t["y"] <= y1]
    if main_towns:
        m = 400
        x0 = max(x0, min(t["x"] for t in main_towns) - m)
        x1 = min(x1, max(t["x"] for t in main_towns) + m)
        y0 = max(y0, min(t["y"] for t in main_towns) - m)
        y1 = min(y1, max(t["y"] for t in main_towns) + m)
    w, h = x1 - x0 + 1, y1 - y0 + 1
    pal = palette()
    for z, t in sorted(tiles.items()):
        if len(t) < 2000:
            continue
        buf = bytearray([0] * (w * h))  # 0 = black, like unexplored automap
        for (x, y), c in t.items():
            if x0 <= x <= x1 and y0 <= y <= y1:
                buf[(y - y0) * w + (x - x0)] = c
        img = Image.frombytes("P", (w, h), bytes(buf))
        img.putpalette(pal)
        img.save(os.path.join(out, f"floor-{z:02d}.png"), optimize=True)
        print(f"floor {z}: {len(t)} tiles")
    json.dump({"x0": x0, "y0": y0, "w": w, "h": h}, open(os.path.join(out, "bounds.json"), "w"))
    json.dump(towns, open(os.path.join(out, "towns.json"), "w"), ensure_ascii=False, indent=1)
    print(f"{len(towns)} towns, map {w}x{h} from {x0},{y0}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
