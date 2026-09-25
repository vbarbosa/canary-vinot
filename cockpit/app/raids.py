"""Raids the game knows: the legacy XML ones (raids/raids.xml) and the Lua ones (scripts/raids/**/*.lua).

Read once from the datapack, with where they happen (for the map photo) and which monsters come.
The panel only sends the raid name; the bridge starts it with the same code as the /raid command.
"""

import glob
import os
import re
import xml.etree.ElementTree as ET
from collections import Counter
from functools import lru_cache

from . import places

LUA_RAID = re.compile(r'Raid\("([^"]+)"')
LUA_AREA = re.compile(r"addArea\(\s*Position\((\d+),\s*(\d+),\s*(\d+)\)")
LUA_MONSTER = re.compile(r'\bname\s*=\s*"([^"]+)"')


def _title(slug):
    return slug.replace("_", " ").replace("-", " ").title()


@lru_cache(maxsize=1)
def all_raids():
    out = []
    base = os.path.join(places.DATAPACK, "raids")
    try:
        for r in ET.parse(os.path.join(base, "raids.xml")).getroot().iter("raid"):
            file = r.get("file", "")
            monsters, pos = Counter(), None
            try:
                for ev in ET.parse(os.path.join(base, file)).getroot():
                    if ev.tag == "singlespawn":
                        monsters[ev.get("name")] += 1
                        pos = pos or (ev.get("x"), ev.get("y"), ev.get("z"))
                    elif ev.tag == "areaspawn":
                        for m in ev.iter("monster"):
                            monsters[m.get("name")] += int(m.get("amount") or 1)
                        pos = pos or ((int(ev.get("fromx")) + int(ev.get("tox"))) // 2, (int(ev.get("fromy")) + int(ev.get("toy"))) // 2, ev.get("fromz"))
            except (OSError, ET.ParseError, TypeError, ValueError):
                pass
            out.append(_raid(r.get("name"), _title(file.split("/")[0]) if "/" in file else "", "xml", monsters, pos))
    except (OSError, ET.ParseError):
        pass
    for path in sorted(glob.glob(os.path.join(places.DATAPACK, "scripts", "raids", "**", "*.lua"), recursive=True)):
        with open(path, encoding="utf-8", errors="replace") as f:
            text = f.read()
        m = LUA_RAID.search(text)
        if not m:
            continue
        area = LUA_AREA.search(text)
        monsters = Counter(LUA_MONSTER.findall(text[m.end():]))
        where = m.group(1).split(".")[0]
        kind = "boss" if os.path.basename(os.path.dirname(path)) == "bosses" else "lua"
        out.append(_raid(m.group(1), _title(where), kind, monsters, area.groups() if area else None))
    # the same Lua raid can be registered by two files: keep the first
    seen, unique = set(), []
    for r in out:
        if r["name"] not in seen:
            seen.add(r["name"])
            unique.append(r)
    return sorted(unique, key=lambda r: (r["where"], r["label"]))


def _raid(name, where, kind, monsters, pos):
    label = _title(name.split(".", 1)[1]) if "." in name else re.sub(r"(?<=[a-z])(?=[A-Z])", " ", name)
    x, y, z = (int(v) for v in pos) if pos else (0, 0, 7)
    return {"name": name, "label": label, "where": where or "—", "kind": kind, "x": x, "y": y, "z": z,
            "monsters": [m for m, _ in monsters.most_common(4)], "amount": sum(monsters.values())}


def search(q="", tipo=""):
    q = q.strip().lower()
    return [r for r in all_raids()
            if (not tipo or r["kind"] == tipo or (tipo == "normal" and r["kind"] != "boss"))
            and (not q or q in r["label"].lower() or q in r["where"].lower() or any(q in m.lower() for m in r["monsters"]))]


def get(name):
    return next((r for r in all_raids() if r["name"] == name), None)
