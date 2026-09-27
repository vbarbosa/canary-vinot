"""Extract one PNG icon per item from the Tibia 13.40 client assets.

Usage (run once, on a machine that has the client assets or internet access):
    python tools/extract_icons.py --assets /path/to/client/assets --out icons/
    python tools/extract_icons.py --download --out icons/

The server's data/items/appearances.dat says which sprite each item uses; the
client's catalog-content.json and sprite sheets (*.bmp.lzma) hold the pixels.
"""

import argparse
import io
import json
import lzma
import os
import sys
import tarfile
import tempfile
import urllib.request

from PIL import Image

ASSETS_TARBALL = "https://github.com/dudantas/tibia-client/archive/refs/tags/13.40.93b0a1.tar.gz"
SPRITE_SIZES = {0: (32, 32), 1: (32, 64), 2: (64, 32), 3: (64, 64)}
HERE = os.path.dirname(os.path.abspath(__file__))


# ------------------------------------------------------------- tiny protobuf reader

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
    """Yield (field_number, wire_type, value) for one protobuf message."""
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


def first_sprites(appearances_path):
    """{item id: first sprite id} for every object in appearances.dat.
    Appearances.object = 1; Appearance.id = 1, .frame_group = 2;
    FrameGroup.sprite_info = 3; SpriteInfo.sprite_id = 5 (repeated, maybe packed)."""
    data = open(appearances_path, "rb").read()
    out = {}
    for num, wt, obj in _fields(data):
        if num != 1 or wt != 2:
            continue
        oid, sprite = None, None
        for n, w, v in _fields(obj):
            if n == 1 and w == 0:
                oid = v
            elif n == 2 and w == 2 and sprite is None:
                for fn, fw, fv in _fields(v):
                    if fn == 3 and fw == 2:
                        for sn, sw, sv in _fields(fv):
                            if sn == 5:
                                sprite = sv if sw == 0 else _varint(sv, 0)[0]
                                break
        if oid is not None and sprite is not None:
            out[oid] = sprite
    return out


# ------------------------------------------------------------- sprite sheets

def decode_sheet(path):
    """CIP sheet: zero padding, 5 constant bytes, 7-bit size, LZMA props, 8 size bytes, raw LZMA1 -> BMP."""
    data = open(path, "rb").read()
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
    lc, lp, pb = d % 9, (d // 9) % 5, d // 45
    dict_size = int.from_bytes(props[1:5], "little")
    filt = {"id": lzma.FILTER_LZMA1, "lc": lc, "lp": lp, "pb": pb, "dict_size": dict_size}
    bmp = lzma.LZMADecompressor(format=lzma.FORMAT_RAW, filters=[filt]).decompress(data[pos:])
    img = Image.open(io.BytesIO(bmp)).convert("RGBA")
    # Some sheets use magenta instead of alpha for transparency.
    px = list(img.getdata())
    if not any(a < 255 for *_, a in px):
        img.putdata([(r, g, b, 0) if (r, g, b) == (255, 0, 255) else (r, g, b, a) for r, g, b, a in px])
    return img


def load_catalog(assets):
    for root, _, files in os.walk(assets):
        if "catalog-content.json" in files:
            return root, json.load(open(os.path.join(root, "catalog-content.json")))
    sys.exit("catalog-content.json not found under " + assets)


def download(dest):
    print("Downloading client assets (large)…", file=sys.stderr)
    path = os.path.join(dest, "assets.tar.gz")
    urllib.request.urlretrieve(ASSETS_TARBALL, path)
    with tarfile.open(path) as tar:
        members = [m for m in tar.getmembers() if m.name.endswith(("catalog-content.json", ".bmp.lzma"))]
        tar.extractall(dest, members=members)
    os.remove(path)
    return dest


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--assets", help="client assets folder (with catalog-content.json)")
    ap.add_argument("--download", action="store_true", help="download the 13.40 assets from GitHub")
    data_dir = os.environ.get("COCKPIT_DATA_DIR", os.path.join(HERE, "..", "..", "data"))
    ap.add_argument("--appearances", default=os.path.join(data_dir, "items", "appearances.dat"))
    ap.add_argument("--items", help="only these item ids (comma separated), for testing")
    ap.add_argument("--out", default=os.environ.get("COCKPIT_ICON_DIR", os.path.join(HERE, "..", "icons")))
    args = ap.parse_args()

    tmp = None
    if args.download:
        tmp = tempfile.mkdtemp()
        args.assets = download(tmp)
    if not args.assets:
        ap.error("use --assets or --download")

    sprites = first_sprites(args.appearances)
    if args.items:
        wanted = {int(i) for i in args.items.split(",")}
        sprites = {k: v for k, v in sprites.items() if k in wanted}
    root, catalog = load_catalog(args.assets)
    sheets = sorted((e for e in catalog if e.get("type") == "sprite"), key=lambda e: e["firstspriteid"])
    os.makedirs(args.out, exist_ok=True)

    by_sheet = {}
    for item_id, sid in sprites.items():
        for e in sheets:
            if e["firstspriteid"] <= sid <= e["lastspriteid"]:
                by_sheet.setdefault(e["file"], (e, []))[1].append((item_id, sid))
                break

    done = 0
    for file, (entry, pairs) in by_sheet.items():
        sheet = decode_sheet(os.path.join(root, file))
        w, h = SPRITE_SIZES.get(entry.get("spritetype", 0), (32, 32))
        cols = sheet.width // w
        for item_id, sid in pairs:
            idx = sid - entry["firstspriteid"]
            x, y = (idx % cols) * w, (idx // cols) * h
            sheet.crop((x, y, x + w, y + h)).save(os.path.join(args.out, f"{item_id}.png"), optimize=True)
            done += 1
    print(f"{done} icons written to {args.out}")


if __name__ == "__main__":
    main()
