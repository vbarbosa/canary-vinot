"""Draws the portal's pixel art into app/static/px as crisp SVGs (and a few PNGs if Pillow is present).

Same identity as the Cockpit logo (cockpit/tools/make_logo.py): the gold-rimmed red shield with
a V, warm gold letters and a night-time Tibia palette.

    python tools/pixelart.py            # write the SVGs
    python tools/pixelart.py --preview  # also write enlarged PNG previews to /tmp/px-preview
"""

import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(__file__))
from heroes import H as HERO_H, W as HERO_W, hero  # noqa: E402

OUT = os.path.join(os.path.dirname(__file__), "..", "app", "static", "px")

P = {
    "K": "#2a1d0e",  # outline
    "S": "#0d0b08",  # shadow
    "G": "#d9a441",  # gold
    "Y": "#f3d27a",  # light gold
    "R": "#8c2a1f",  # red
    "r": "#5e1a13",  # dark red
    "W": "#fff4d6",  # cream
    "E": "#a9a9b4",  # steel
    "e": "#5d5d6b",  # dark steel
    "M": "#7a4a24",  # wood
    "m": "#4e2e15",  # dark wood
    "N": "#4b8b3b",  # green
    "n": "#2f5a26",  # dark green
    "L": "#8fcf5a",  # light green
    "B": "#3b6fb6",  # blue
    "b": "#24406b",  # dark blue
    "C": "#8fe3f2",  # cyan
    "V": "#8a55c7",  # violet
    "v": "#4a2b73",  # dark violet
    "O": "#e8b48a",  # skin
    "o": "#b97f58",  # skin shade
    "F": "#ff8a3d",  # flame
}

SPRITES = {
    # The VinOT shield, identical to the Cockpit emblem.
    "emblem": [
        ".KKKKKKKKKKKKKK.",
        "KGGGGGGGGGGGGGGK",
        "KGYRRRRRRRRRRRGK",
        "KGRWWRRRRRRWWrGK",
        "KGRWWRRRRRRWWrGK",
        "KGRrWWRRRRWWrrGK",
        "KGRrWWRRRRWWrrGK",
        "KGRRrWWRRWWrrrGK",
        ".KGRrWWRRWWrrGK.",
        ".KGRRrWWWWrrrGK.",
        "..KGRrWWWWrrGK..",
        "..KGRRrWWrrrGK..",
        "...KGRRrrrrGK...",
        "....KGGrrGGK....",
        ".....KGGGGK.....",
        "......KKKK......",
    ],
    "sword": [
        ".............KKK",
        "............KWWK",
        "...........KWEeK",
        "..........KWEeK.",
        ".........KWEeK..",
        "........KWEeK...",
        ".......KWEeK....",
        "..KK..KWEeK.....",
        "..KGKKWEeK......",
        "...KGWEeK.......",
        "....KGeK........",
        "...KMKGGK.......",
        "..KMmK.KGK......",
        ".KMmK...KK......",
        "KYmK............",
        ".KK.............",
    ],
    "bow": [
        ".....KKK........",
        "....KMMWK.......",
        "...KMmK.W.......",
        "...KMK..W.......",
        "..KMmK...W......",
        "..KMK....W....KK",
        "..KMK.....W.KEeK",
        "..KGK..KKKKKEEK.",
        "..KGK.KWWWWWWK..",
        "..KMK.....WKK...",
        "..KMK....W.K....",
        "..KMmK...W......",
        "...KMK..W.......",
        "...KMmK.W.......",
        "....KMMWK.......",
        ".....KKK........",
    ],
    "staff": [
        "......KKKK......",
        ".....KVCCVK.....",
        "....KVCWCVvK....",
        "....KVCCVVvK....",
        "....KvVVVvvK....",
        ".....KvvvvK.....",
        "......KGGK......",
        "......KMmK......",
        "......KMmK......",
        "......KMmK......",
        "......KGGK......",
        "......KMmK......",
        "......KMmK......",
        "......KMmK......",
        "......KmmK......",
        ".......KK.......",
    ],
    "druid": [
        "....KK...KK.....",
        "...KLNK.KLNK....",
        "...KNnK.KNnK....",
        "....KNKKKnK.....",
        ".....KMLLK......",
        "......KMK.KK....",
        "......KMKKLNK...",
        "......KMmKNnK...",
        "......KMmKKK....",
        "......KMmK......",
        "......KMmK......",
        "......KMmK......",
        "......KMmK......",
        "......KMmK......",
        "......KmmK......",
        ".......KK.......",
    ],
    "potion": [
        "......KKKK......",
        "......KMmK......",
        ".....KKKKKK.....",
        "......KWEK......",
        "......KWEK......",
        ".....KWRRRK.....",
        "....KWRRRRRK....",
        "...KWRRRRRRrK...",
        "...KWRYRRRRrK...",
        "...KRYRRRRRrK...",
        "...KRRRRRRrrK...",
        "...KRRRRRRrrK...",
        "....KrRRRrrK....",
        ".....KKKKKK.....",
        "................",
        "................",
    ],
    "chest": [
        "................",
        "................",
        "...KKKKKKKKKK...",
        "..KMMMMMMMMMMK..",
        ".KMMmmmmmmmmMMK.",
        ".KGGGGGGGGGGGGK.",
        ".KMMMMKYYKMMMMK.",
        ".KKKKKKGGKKKKKK.",
        ".KMMMMKGGKMMMMK.",
        ".KMmmmKKKKmmmMK.",
        ".KMmmmmmmmmmmMK.",
        ".KGMmmmmmmmmMGK.",
        ".KGMMMMMMMMMMGK.",
        ".KKKKKKKKKKKKKK.",
        "..S..........S..",
        "................",
    ],
    "coin": [
        "................",
        ".....KKKKKK.....",
        "....KYYYYYGK....",
        "...KYYGGGGGGK...",
        "..KYmGGGGGGmGK..",
        "..KYmGGGGGGmGK..",
        "..KYGmGGGGmGGK..",
        "..KYGmGGGGmGGK..",
        "..KYGGmGGmGGGK..",
        "..KYGGGmmGGGGK..",
        "..KYGGGGGGGGmK..",
        "...KGGGGGGGmK...",
        "....KGGGGGmK....",
        ".....KKKKKK.....",
        "................",
        "................",
    ],
    "scroll": [
        "................",
        "..KKKKKKKKKKKK..",
        ".KWWWWWWWWWWWYK.",
        ".KYKKKKKKKKKKYK.",
        "..KWWWWWWWWWWK..",
        "..KWmmmmmmWWWK..",
        "..KWWWWWWWWWWK..",
        "..KWmmmmmmmmWK..",
        "..KWWWWWWWWWWK..",
        "..KWmmmmmWWWWK..",
        "..KWWWWWWWWWWK..",
        "..KWmmmmmmmWWK..",
        ".KYKKKKKKKKKKYK.",
        ".KWWWWWWWWWWWYK.",
        "..KKKKKKKKKKKK..",
        "................",
    ],
    "gift": [
        "................",
        "....KK....KK....",
        "...KGYK..KYGK...",
        "...KGGYKKYGGK...",
        "....KKGYYGKK....",
        ".KKKKKKGGKKKKKK.",
        ".KRRRRRGGRRRRRK.",
        ".KRRRRRGGRRRRrK.",
        ".KKKKKKGGKKKKKK.",
        "..KRRRRGGRRRrK..",
        "..KRRRRGGRRRrK..",
        "..KRRRRGGRRRrK..",
        "..KrRRRGGRRrrK..",
        "..KrrrrGGrrrrK..",
        "..KKKKKKKKKKKK..",
        "................",
    ],
    "heart": [
        "................",
        "................",
        "...KKK...KKK....",
        "..KRRRK.KRRRK...",
        ".KRWWRRKRRRRrK..",
        ".KRWRRRRRRRRrK..",
        ".KRRRRRRRRRRrK..",
        ".KRRRRRRRRRrrK..",
        "..KRRRRRRRRrK...",
        "...KRRRRRRrK....",
        "....KRRRRrK.....",
        ".....KRRrK......",
        "......KrK.......",
        ".......K........",
        "................",
        "................",
    ],
    "key": [
        "................",
        "...KKKK.........",
        "..KYGGGK........",
        ".KYK..KGK.......",
        ".KGK..KGK.......",
        ".KGGKKGGK.......",
        "..KGGGGKKK......",
        "...KKKKGGGK.....",
        ".......KGGGK....",
        "........KGGGK...",
        ".........KGGGK..",
        "........KGKGGK..",
        ".......KGK.KK...",
        "........K.......",
        "................",
        "................",
    ],
    "map": [
        "................",
        ".KKKKKKKKKKKKKK.",
        ".KWWWWKWWWWKWWK.",
        ".KWNNWKWBBWKWWK.",
        ".KWNNNKWBBBKWNK.",
        ".KWWNWKWWBWKNNK.",
        ".KWWWWKRWWWKWWK.",
        ".KWWWRKWRWWKWWK.",
        ".KWWWWKWWRWKWWK.",
        ".KWNWWKWWWRKRWK.",
        ".KNNNWKWWWWKWRK.",
        ".KWNWWKWBWWKWWK.",
        ".KWWWWKBBBWKWWK.",
        ".KKKKKKKKKKKKKK.",
        "................",
        "................",
    ],
    "skull": [
        "................",
        ".....KKKKKK.....",
        "....KWWWWWWK....",
        "...KWWWWWWWEK...",
        "...KWWWWWWWEK...",
        "...KWKKWWKKEK...",
        "...KWKKWWKKEK...",
        "...KWWWKKWWEK...",
        "....KWWWWWEK....",
        ".....KWKWKK.....",
        ".....KKKKK......",
        "................",
        "................",
        "................",
        "................",
        "................",
    ],
    # Vini, the mascot: a little knight with the VinOT shield and a red cape.
    "mascot": [
        "......KKKK......",
        ".....KEEEEK.....",
        "....KEWEEEeK....",
        "....KEKKKKeK....",
        "....KEKOOKeK....",
        "....KEeeeeeK....",
        "...KRKeeeeKRK...",
        "..KRRKEEEEKRRK..",
        ".KGGGKEWEEKRrK..",
        "KGWRWGKEEeKORK..",
        "KGWRWGKEEeKOrK..",
        "KGRWRGKeeeKKrK..",
        ".KGGGKMMMMKrrK..",
        "..KGK.KeKeK.K...",
        "......KeKeK.....",
        ".....KmK.KmK....",
    ],
    "torch": [
        "......K.........",
        ".....KFK........",
        "....KFYFK.......",
        "....KFYYFK......",
        "...KFYWYFK......",
        "...KFYWYFK......",
        "....KFYFK.......",
        ".....KGK........",
        ".....KMK........",
        ".....KMK........",
        ".....KMK........",
        ".....KmK........",
        ".....KmK........",
        ".....KmK........",
        ".....KKK........",
        "................",
    ],
}

FONT = {
    "V": ["X...X", "X...X", "X...X", "X...X", ".X.X.", ".X.X.", "..X.."],
    "i": ["X", ".", "X", "X", "X", "X", "X"],
    "n": ["....", "....", "XXX.", "X..X", "X..X", "X..X", "X..X"],
    "O": [".XXX.", "X...X", "X...X", "X...X", "X...X", "X...X", ".XXX."],
    "T": ["XXXXX", "..X..", "..X..", "..X..", "..X..", "..X..", "..X.."],
}


def grid_pixels(rows, dx=0, dy=0):
    return [(dx + x, dy + y, P[c]) for y, row in enumerate(rows) for x, c in enumerate(row) if c != "."]


def word_pixels(text, dx, dy):
    out, x = [], dx
    for ch in text:
        glyph = FONT[ch]
        for y, row in enumerate(glyph):
            for gx, c in enumerate(row):
                if c == "X":
                    out.append((x + gx + 1, dy + y + 1, P["S"]))
        for y, row in enumerate(glyph):
            for gx, c in enumerate(row):
                if c == "X":
                    out.append((x + gx, dy + y, P["Y"] if y < 3 else P["G"]))
        x += len(glyph[0]) + 1
    return out, x


def svg(pixels, w, h, extra=""):
    """Pixels -> SVG, merging horizontal runs of the same colour so files stay small."""
    grid = {}
    for x, y, c in pixels:
        grid[(x, y)] = c  # later pixels win
    rects = []
    for y in range(h):
        x = 0
        while x < w:
            c = grid.get((x, y))
            if not c:
                x += 1
                continue
            run = 1
            while grid.get((x + run, y)) == c:
                run += 1
            rects.append(f'<rect x="{x}" y="{y}" width="{run}" height="1" fill="{c}"/>')
            x += run
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" shape-rendering="crispEdges">'
        + extra + "".join(rects) + "</svg>\n"
    )


def scene(w=240, h=90, seed=7):
    """Night skyline: stars, moon, mountains, a castle with lit windows and the VinOT flag, pine hills."""
    rnd = random.Random(seed)
    px = []
    bands = ["#0d0b1a", "#130f24", "#1a1330", "#22173a", "#2b1b40", "#361f44"]
    band_h = h * 0.75 / len(bands)
    for y in range(h):
        i = min(int(y / band_h), len(bands) - 1)
        nxt = min(i + 1, len(bands) - 1)
        # dither the band edges
        frac = (y / band_h) - int(y / band_h)
        for x in range(w):
            c = bands[nxt] if frac > 0.7 and (x + y) % 2 == 0 else bands[i]
            px.append((x, y, c))
    for _ in range(90):
        x, y = rnd.randrange(w), rnd.randrange(int(h * 0.55))
        px.append((x, y, rnd.choice(["#fff4d6", "#f3d27a", "#8fe3f2", "#ffffff"])))
    for _ in range(6):  # bigger twinkles
        x, y = rnd.randrange(4, w - 4), rnd.randrange(3, int(h * 0.4))
        for dx, dy in ((0, 0), (1, 0), (-1, 0), (0, 1), (0, -1)):
            px.append((x + dx, y + dy, "#fff4d6" if (dx, dy) == (0, 0) else "#f3d27a"))
    mx, my, mr = int(w * 0.82), 16, 9
    for y in range(my - mr, my + mr + 1):
        for x in range(mx - mr, mx + mr + 1):
            d = math.hypot(x - mx, y - my)
            if d <= mr:
                c = "#fff4d6" if d < mr - 1 else "#f3d27a"
                if math.hypot(x - mx - 3, y - my + 2) < 2 or math.hypot(x - mx + 2, y - my - 3) < 1.5:
                    c = "#e6d3a6"
                px.append((x, y, c))
    # far mountains
    for x in range(w):
        top = int(h * 0.52 + 9 * math.sin(x / 17.0) + 5 * math.sin(x / 7.3 + 1))
        for y in range(top, h):
            px.append((x, y, "#2a1e3f" if y > top else "#3b2b55"))
    # castle
    cx, base = w // 2, int(h * 0.78)
    wall_top = base - 18

    def block(x0, x1, y0, c="#1b1424"):
        for yy in range(y0, base + 1):
            for xx in range(x0, x1):
                px.append((xx, yy, c))

    def merlons(x0, x1, y0):
        for xx in range(x0, x1):
            if (xx - x0) % 4 < 2:
                px.append((xx, y0 - 1, "#1b1424"))
                px.append((xx, y0 - 2, "#1b1424"))

    block(cx - 40, cx + 40, wall_top)
    merlons(cx - 40, cx + 40, wall_top)
    for tx, tw, th in ((cx - 44, 12, 34), (cx + 32, 12, 34), (cx - 8, 16, 50)):
        top = base - th
        block(tx, tx + tw, top)
        merlons(tx, tx + tw, top)
        for wy in range(top + 5, base - 8, 9):  # lit windows
            for wx in (tx + tw // 2 - 1,):
                for dy in range(3):
                    px.append((wx, wy + dy, "#f3d27a"))
                    px.append((wx + 1, wy + dy, "#d9a441" if dy else "#f3d27a"))
    # central spire + flag with the V
    top = base - 50
    for i in range(8):
        for xx in range(cx - 7 + i, cx + 9 - i):
            px.append((xx, top - 2 - i, "#1b1424"))
    pole_top = top - 18
    for yy in range(pole_top, top - 9):
        px.append((cx, yy, "#7a4a24"))
    flag = ["RRRRRRRRRR", "RWRRRRRWRR", "RRWRRRWRRR", "RRRWRWRRRr", "RRRRWRRRrr", "RRRRRRRr.."]
    for fy, row in enumerate(flag):
        for fx, c in enumerate(row):
            if c != ".":
                px.append((cx + 1 + fx, pole_top + fy, P[c]))
    # gate with warm light
    for yy in range(base - 9, base + 1):
        for xx in range(cx - 4, cx + 4):
            if yy > base - 8 or abs(xx - cx + 0.5) < 3:
                px.append((xx, yy, "#d9a441" if yy > base - 3 else "#f3d27a"))
    # wall windows
    for wx in range(cx - 34, cx + 34, 8):
        if abs(wx - cx) > 10:
            px.append((wx, wall_top + 6, "#f3d27a"))
            px.append((wx, wall_top + 7, "#d9a441"))
    # near hills and pines
    for x in range(w):
        top = int(h * 0.84 + 3 * math.sin(x / 11.0 + 2) + 2 * math.sin(x / 4.1))
        for y in range(top, h):
            px.append((x, y, "#1f3a22" if y > top + 1 else "#2f5a26"))
    for tx in list(range(4, cx - 50, 13)) + list(range(cx + 52, w - 4, 13)):
        tx += rnd.randrange(-3, 4)
        th = rnd.randrange(10, 17)
        tb = int(h * 0.86)
        for i in range(th):
            half = max(0, (i * 5) // th)
            for xx in range(tx - half, tx + half + 1):
                c = "#2f5a26" if xx < tx else "#1f3a22"
                px.append((xx, tb - th + i, c))
        px.append((tx, tb, "#4e2e15"))
        px.append((tx, tb + 1, "#4e2e15"))
    return px


def ground(w=32, h=12):
    """Repeating grass-and-dirt strip for section edges."""
    px = []
    for x in range(w):
        tip = 2 + (1 if x % 3 == 0 else 0) - (1 if x % 7 == 0 else 0)
        for y in range(h):
            if y < tip:
                continue
            if y < tip + 3:
                c = "#8fcf5a" if y == tip else "#4b8b3b"
            else:
                c = "#7a4a24" if (x * 3 + y * 5) % 11 else "#4e2e15"
            px.append((x, y, c))
    return px


def main(preview=False):
    os.makedirs(OUT, exist_ok=True)
    outputs = {}
    for name, rows in SPRITES.items():
        outputs[name] = (grid_pixels(rows), len(rows[0]), len(rows))
    word, end = word_pixels("VinOT", 20, 4)
    outputs["logo"] = (grid_pixels(SPRITES["emblem"]) + word, end + 1, 16)
    outputs["ground"] = (ground(), 32, 12)
    for voc in ("knight", "paladin", "sorcerer", "druid"):
        outputs[f"hero-{voc}"] = (hero(voc, P), HERO_W, HERO_H)
    for name, (pixels, w, h) in outputs.items():
        with open(os.path.join(OUT, f"{name}.svg"), "w") as f:
            f.write(svg(pixels, w, h))
    try:
        from PIL import Image
    except ImportError:
        return
    def png(pixels, w, h, scale):
        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        for x, y, c in pixels:
            if 0 <= x < w and 0 <= y < h:
                img.putpixel((x, y), tuple(int(c[i:i + 2], 16) for i in (1, 3, 5)) + (255,))
        return img.resize((w * scale, h * scale), Image.NEAREST)
    static = os.path.join(OUT, "..")
    png(*outputs["emblem"], 2).save(os.path.join(static, "favicon.png"))
    png(grid_pixels(SPRITES["emblem"], 1, 1), 18, 18, 10).save(os.path.join(static, "apple-touch-icon.png"))
    # social preview card
    card = Image.new("RGBA", (1200, 630), (21, 19, 15, 255))
    scene_px = (scene(), 240, 90)
    png(*scene_px, 1).save(os.path.join(OUT, "scene.png"))
    card.alpha_composite(png(*scene_px, 5).crop((0, 0, 1200, 450)), (0, 180))
    lg = png(*outputs["logo"], 12)
    card.alpha_composite(lg, ((1200 - lg.width) // 2, 40))
    card.convert("RGB").save(os.path.join(static, "og.png"))
    if preview:
        d = "/tmp/px-preview"
        os.makedirs(d, exist_ok=True)
        sheet = Image.new("RGBA", (18 * 10 * 8, 18 * 10 * 2 + 20), (40, 40, 40, 255))
        for i, name in enumerate(SPRITES):
            pix, w, h = outputs[name]
            sheet.alpha_composite(png(pix, w, h, 10), ((i % 8) * 180, (i // 8) * 180))
        sheet.save(os.path.join(d, "sprites.png"))
        png(*scene_px, 4).save(os.path.join(d, "scene.png"))
        png(*outputs["logo"], 8).save(os.path.join(d, "logo.png"))


if __name__ == "__main__":
    main(preview="--preview" in sys.argv)
