"""Full-body pixel heroes for the four vocations, built from one body template plus
per-vocation colours and props. Imported by tools/pixelart.py."""

# 20x25 body, front view. Letters are recoloured per vocation:
# H/h headgear, O/o skin, T/t outfit, A trim, L/l legs, B/b boots.
BODY = [
    "......KKKKKKK.......",
    ".....KHHHHHHHK......",
    "....KHHHHHHHHhK.....",
    "....KHHHHHHHHhK.....",
    "....KKKKKKKKKKK.....",
    "....KOOOOOOOOoK.....",
    "....KOKKOOOKKoK.....",
    "....KOOOOOOOOoK.....",
    ".....KOOooOOoK......",
    "......KKOOOKK.......",
    "....KKTTAAATTKK.....",
    "...KTTTTAAATTttK....",
    "..KOKTTTAAATTtKOK...",
    "..KOKTTTTTTTTtKOK...",
    "..KOKTTTTTTTttKOK...",
    "..KoKAAAAAAAAAKoK...",
    "...KKTTTTTTTttKK....",
    "....KTTTTTTTttK.....",
    "....KLLLLKLLLlK.....",
    "....KLLLLKLLLlK.....",
    "....KLLLlKLLLlK.....",
    "....KLLLlKLLLlK.....",
    "....KBBBBKBBBBK.....",
    "...KBBBBbKBBBBbK....",
    "...KKKKKKKKKKKKK....",
]

W, H = 28, 34
BX, BY = 4, 6  # where the body sits on the canvas

LOOKS = {
    "knight": {"H": "E", "h": "e", "T": "R", "t": "r", "A": "G", "L": "e", "l": "S", "B": "m", "b": "K"},
    "paladin": {"H": "N", "h": "n", "T": "N", "t": "n", "A": "M", "L": "M", "l": "m", "B": "m", "b": "K"},
    "sorcerer": {"H": "V", "h": "v", "T": "V", "t": "v", "A": "G", "L": "V", "l": "v", "B": "v", "b": "K"},
    "druid": {"H": "n", "h": "S", "T": "N", "t": "n", "A": "Y", "L": "N", "l": "n", "B": "M", "b": "m"},
}

# Props: (x, y, rows) drawn on top of the body, "." is transparent.
PROPS = {
    "knight": [
        (9, 2, [  # red plume on the helmet
            "..KKK..",
            ".KRRRK.",
            "KRRrRK.",
            ".KKKK..",
        ]),
        (8, 10, ["KEEEEEEK", "KeKKKKeK"]),  # visor
        (18, 7, [  # sword raised in the right hand
            "..KK.",
            ".KWEK",
            ".KWeK",
            ".KWeK",
            ".KWeK",
            ".KWeK",
            ".KWeK",
            ".KWeK",
            ".KWeK",
            ".KWeK",
            "KGGGGK",
            ".KMK.",
            ".KMK.",
            ".KYK.",
        ]),
        (0, 16, [  # the VinOT shield on the left arm
            "KKKKKKKK",
            "KGGGGGGK",
            "KWRRRRWK",
            "KRWRRWrK",
            "KRRWWrrK",
            ".KRWWrK.",
            "..KGGK..",
            "...KK...",
        ]),
    ],
    "paladin": [
        (8, 3, ["..KK..", ".KNNK.", "KNNnnK"]),  # hood tip
        (6, 16, ["K", "K", "K"]),
        (2, 7, [  # quiver with arrows over the left shoulder
            "...W.W",
            "..KWKW",
            "..KMMK",
            ".KMmK.",
            ".KMmK.",
            "KMmK..",
        ]),
        (19, 12, [  # bow in the right hand
            "..KK...",
            ".KMMK..",
            ".KMK.W.",
            "KMK..W.",
            "KMK..W.",
            "KMK..W.",
            "KMK..W.",
            "KGK..W.",
            "KGK..W.",
            "KMK..W.",
            "KMK..W.",
            "KMK..W.",
            "KMK..W.",
            ".KMK.W.",
            ".KMMK..",
            "..KK...",
        ]),
    ],
    "sorcerer": [
        (7, 0, [  # tall pointed hat
            "......KK...",
            ".....KVVK..",
            "....KVVvK..",
            "....KVYvK..",
            "...KVVVvvK.",
            "...KVVVvvK.",
            "..KVVVVVvvK",
        ]),
        (6, 10, ["KGGGGGGGGGGGK", ".KKKKKKKKKKK."]),  # hat brim
        (18, 1, [  # staff with a glowing orb
            ".KKKK.",
            "KCCWCK",
            "KCWCCK",
            "KCCCVK",
            ".KVVK.",
            "..KGK.",
            "..KMK.",
            "..KMK.",
            "..KMK.",
            "..KMK.",
            "..KMK.",
            "..KMK.",
            "..KMK.",
            "..KMK.",
            "..KMK.",
            "..KMK.",
            "..KMK.",
            "..KMK.",
            "..KMK.",
            "..KmK.",
            "..KmK.",
            "..KmK.",
            "..KmK.",
            "..KmK.",
            "...K..",
        ]),
        (3, 18, [  # fireball in the left hand
            ".KFK.",
            "KFYFK",
            "KYWYK",
            ".KFK.",
        ]),
    ],
    "druid": [
        (8, 3, ["..KK..", ".KnnK.", "KnnSSK"]),  # hood tip
        (7, 7, ["...KLK", "..KLNK", "...KK."]),  # leaf on the hood
        (16, 2, [  # living staff with leaves
            "KK..KK",
            "KLK.KLK",
            ".KNKNK",
            "..KMK.",
            ".KLKMK",
            "KLNKMK",
            ".KK.MK",
            "...KMK",
            "...KMK",
            "...KMK",
            "...KMK",
            "...KMK",
            "...KMK",
            "...KMK",
            "...KMK",
            "...KMK",
            "...KMK",
            "...KMK",
            "...KMK",
            "...KMK",
            "...KmK",
            "...KmK",
            "...KmK",
            "...KmK",
            "....K.",
        ]),
        (3, 18, [  # healing sparkle in the left hand
            "..C..",
            ".CWC.",
            "CWWWC",
            ".CWC.",
            "..C..",
        ]),
    ],
}


def hero(vocation, palette):
    """Pixels (x, y, colour) for one vocation, body first and props on top."""
    look = LOOKS[vocation]
    px = []
    for y, row in enumerate(BODY):
        for x, c in enumerate(row):
            if c != ".":
                px.append((BX + x, BY + y, palette[look.get(c, c)]))
    for ox, oy, rows in PROPS[vocation]:
        for y, row in enumerate(rows):
            for x, c in enumerate(row):
                if c != ".":
                    px.append((ox + x, oy + y, palette[c]))
    # the right hand is drawn again so it grips the weapon
    for y, row in enumerate(["KOK", "KOK", "KoK"]):
        for x, c in enumerate(row):
            px.append((BX + 14 + x, BY + 12 + y, palette[c]))
    return px
