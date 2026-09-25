"""Draws the VinOT pixel-art logo from the grids below into app/static (SVG, plus PNG icons if Pillow is present).

    python tools/make_logo.py                      # panel assets
    python tools/make_logo.py --client ../vinot-client   # game client icons (Windows .ico, Android launcher, login logo)
"""

import os
import sys

OUT = os.path.join(os.path.dirname(__file__), "..", "app", "static")
COLORS = {"K": "#2a1d0e", "G": "#d9a441", "Y": "#f3d27a", "R": "#8c2a1f", "r": "#5e1a13", "W": "#fff4d6", "S": "#0d0b08"}

# 16x16 shield with a V (VinOT, Vinicius)
EMBLEM = [
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
]

FONT = {
    "V": ["X...X", "X...X", "X...X", "X...X", ".X.X.", ".X.X.", "..X.."],
    "i": ["X", ".", "X", "X", "X", "X", "X"],
    "n": ["....", "....", "XXX.", "X..X", "X..X", "X..X", "X..X"],
    "O": [".XXX.", "X...X", "X...X", "X...X", "X...X", "X...X", ".XXX."],
    "T": ["XXXXX", "..X..", "..X..", "..X..", "..X..", "..X..", "..X.."],
}


def emblem_pixels(dx=0, dy=0):
    return [(dx + x, dy + y, COLORS[c]) for y, row in enumerate(EMBLEM) for x, c in enumerate(row) if c != "."]


def word_pixels(text, dx, dy):
    out, x = [], dx
    for ch in text:
        glyph = FONT[ch]
        for y, row in enumerate(glyph):
            for gx, c in enumerate(row):
                if c == "X":
                    out.append((x + gx + 1, dy + y + 1, COLORS["S"]))  # drop shadow first
        for y, row in enumerate(glyph):
            for gx, c in enumerate(row):
                if c == "X":
                    out.append((x + gx, dy + y, COLORS["Y"] if y < 3 else COLORS["G"]))
        x += len(glyph[0]) + 1
    return out, x


def svg(pixels, w, h):
    rects = "".join(f'<rect x="{x}" y="{y}" width="1" height="1" fill="{c}"/>' for x, y, c in pixels)
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" shape-rendering="crispEdges">{rects}</svg>\n'


def png(pixels, w, h, scale, path):
    try:
        from PIL import Image
    except ImportError:
        return
    img = Image.new("RGBA", (w * scale, h * scale), (0, 0, 0, 0))
    for x, y, c in pixels:
        rgb = tuple(int(c[i : i + 2], 16) for i in (1, 3, 5))
        for px in range(scale):
            for py in range(scale):
                img.putpixel((x * scale + px, y * scale + py), rgb + (255,))
    img.save(path)


def main():
    em = emblem_pixels()
    with open(os.path.join(OUT, "emblem.svg"), "w") as f:
        f.write(svg(em, 16, 16))
    word, end = word_pixels("VinOT", 20, 4)
    with open(os.path.join(OUT, "logo.svg"), "w") as f:
        f.write(svg(em + word, end + 1, 16))
    word_only, end_only = word_pixels("VinOT", 0, 0)
    with open(os.path.join(OUT, "wordmark.svg"), "w") as f:
        f.write(svg(word_only, end_only, 8))
    png(em, 16, 16, 2, os.path.join(OUT, "favicon.png"))
    png(emblem_pixels(1, 1), 18, 18, 10, os.path.join(OUT, "apple-touch-icon.png"))


def image(pixels, w, h, scale):
    from PIL import Image

    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    for x, y, c in pixels:
        img.putpixel((x, y), tuple(int(c[i : i + 2], 16) for i in (1, 3, 5)) + (255,))
    return img.resize((w * scale, h * scale), Image.NEAREST)


def on_tile(size, pad, shape="square", bg=(21, 19, 15, 255)):
    """The emblem centred on a dark tile (launcher icons)."""
    from PIL import Image, ImageDraw

    tile = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(tile)
    if shape == "circle":
        d.ellipse((0, 0, size - 1, size - 1), fill=bg)
    elif shape == "square":
        d.rounded_rectangle((0, 0, size - 1, size - 1), radius=size // 6, fill=bg)
    scale = max(1, (size - 2 * pad) // 16)
    em = image(emblem_pixels(), 16, 16, scale)
    tile.alpha_composite(em, ((size - em.width) // 2, (size - em.height) // 2))
    return tile


def client(root):
    res = os.path.join(root, "android", "app", "src", "main", "res")
    image(emblem_pixels(), 16, 16, 64).save(os.path.join(root, "data", "images", "clienticon.png"))
    word, end = word_pixels("VinOT", 20, 4)
    image(emblem_pixels() + word, end + 1, 16, 8).save(os.path.join(root, "data", "images", "vinot_logo.png"))
    ico = on_tile(256, 8, shape=None)
    for path in ("src/otcicon.ico", "cmake/icon/otcicon.ico"):
        ico.save(os.path.join(root, path), sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    for folder, size in {"mdpi": 48, "hdpi": 72, "xhdpi": 96, "xxhdpi": 144, "xxxhdpi": 192}.items():
        d = os.path.join(res, f"mipmap-{folder}")
        os.makedirs(d, exist_ok=True)
        on_tile(size, size // 8).save(os.path.join(d, "ic_launcher.webp"), lossless=True)
        on_tile(size, size // 6, shape="circle").save(os.path.join(d, "ic_launcher_round.webp"), lossless=True)
    # adaptive icon (Android 8+): 108dp foreground with the emblem inside the 66dp safe zone
    fg = os.path.join(res, "drawable-nodpi")
    os.makedirs(fg, exist_ok=True)
    on_tile(432, 112, shape=None).save(os.path.join(fg, "ic_launcher_foreground.png"))


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--client":
        client(sys.argv[2])
    else:
        main()
