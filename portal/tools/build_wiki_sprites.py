"""Draw the wiki's creature and item pictures from the Tibia 13.40 client assets.

    python tools/build_wiki_sprites.py            # only what is missing
    python tools/build_wiki_sprites.py --force    # redo everything

Creatures go to app/static/wiki/c/<slug>.png (standing, facing south, with the outfit colours and
addons from the monster file) and loot items to app/static/wiki/i/<id>.png, at the client's own
size; the pages enlarge them with nearest-neighbour. Only the sprite sheets that are needed are
downloaded, from the same assets tag the game client is built from. Run it after adding creatures.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, HERE)

from PIL import Image  # noqa: E402

import extract_creatures as ec  # noqa: E402
from app import wiki  # noqa: E402

OUT = os.path.join(HERE, "..", "app", "static", "wiki")
APPEARANCES = os.path.join(wiki.GAME, "data", "items", "appearances.dat")


def infos(kind, wanted):
    """{id: dict(px, py, pz, layers, ids)} of the first frame group, for objects (1) or outfits (2)."""
    out = {}
    for num, wt, obj in ec._fields(open(APPEARANCES, "rb").read()):
        if num != kind or wt != 2:
            continue
        oid, info = None, None
        for n, w, v in ec._fields(obj):
            if n == 1 and w == 0:
                oid = v
            elif n == 2 and w == 2 and info is None:
                for fn, fw, fv in ec._fields(v):
                    if fn == 3 and fw == 2:
                        info = {"px": 1, "py": 1, "pz": 1, "layers": 1, "ids": []}
                        for sn, sw, sv in ec._fields(fv):
                            key = {1: "px", 2: "py", 3: "pz", 4: "layers"}.get(sn)
                            if key:
                                info[key] = sv
                            elif sn == 5:
                                info["ids"] += ec._packed(sw, sv)
        if oid in wanted and info and info["ids"]:
            out[oid] = info
    return out


def trim(img):
    box = img.getbbox()
    return img.crop(box) if box else None


def main(force=False):
    d = wiki.data()
    os.makedirs(os.path.join(OUT, "c"), exist_ok=True)
    os.makedirs(os.path.join(OUT, "i"), exist_ok=True)
    todo_c = [c for c in d["creatures"] if force or not os.path.exists(os.path.join(OUT, "c", c["slug"] + ".png"))]
    todo_i = [i for i in d["drops"] if force or not os.path.exists(os.path.join(OUT, "i", f"{i}.png"))]
    todo_i += [c["looktype_ex"] for c in todo_c if c["looktype_ex"]]
    if EXTRA_ITEMS:  # e.g. every weapon/armor the MediaWiki export lists, not only loot
        todo_i += [i for i in EXTRA_ITEMS if i not in todo_i and (force or not os.path.exists(os.path.join(OUT, "i", f"{i}.png")))]
    print(f"{len(todo_c)} creatures and {len(todo_i)} items to draw")
    outfits = infos(2, {c["looktype"] for c in todo_c if c["looktype"]})
    objects = infos(1, set(todo_i))
    sprites = ec.Sprites()
    done = 0

    def item_img(iid):
        info = objects.get(iid)
        if not info:
            return None
        base = sprites.get(info["ids"][0])
        return trim(base) if base else None

    for c in todo_c:
        img = None
        try:
            if c["looktype"] and c["looktype"] in outfits:
                info = outfits[c["looktype"]]
                colors = dict(zip(("head", "body", "legs", "feet"), (ec.outfit_color(v) for v in c["colors"])))
                addons = tuple(a for a, bit in ((1, 1), (2, 2)) if c["addons"] & bit)
                img = ec.render_outfit(sprites, info, colors, addons=addons, direction=2 if info["px"] > 2 else 0)
                img = trim(img) if img else None
            elif c["looktype_ex"]:
                img = item_img(c["looktype_ex"])
        except Exception as exc:
            print("failed", c["name"], exc, file=sys.stderr)
        if img:
            img.save(os.path.join(OUT, "c", c["slug"] + ".png"), optimize=True)
            done += 1
    for iid in set(todo_i):
        try:
            img = item_img(iid)
        except Exception as exc:
            print("failed item", iid, exc, file=sys.stderr)
            img = None
        if img:
            img.save(os.path.join(OUT, "i", f"{iid}.png"), optimize=True)
            done += 1
    print(f"drew {done} pictures, {len(sprites.cache)} sheets downloaded")


EXTRA_ITEMS = []

if __name__ == "__main__":
    if "--extra-items" in sys.argv:
        with open(sys.argv[sys.argv.index("--extra-items") + 1]) as f:
            EXTRA_ITEMS = [int(x) for x in f.read().split() if x.isdigit()]
    main(force="--force" in sys.argv)
