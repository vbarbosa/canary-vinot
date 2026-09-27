"""Raids the game knows: the legacy XML ones (raids/raids.xml) and the Lua ones (scripts/raids/**/*.lua).

Read once from the datapack, with where they happen (for the map photo) and which monsters come.
The panel only sends the raid name; the bridge starts it with the same code as the /raid command.
"""

import glob
import os
import re
import time
import xml.etree.ElementTree as ET
from collections import Counter
from functools import lru_cache

from . import db, places

LUA_RAID = re.compile(r'Raid\("([^"]+)"')
LUA_AREA = re.compile(r"addArea\(\s*Position\((\d+),\s*(\d+),\s*(\d+)\)")
LUA_MONSTER = re.compile(r'\bname\s*=\s*"([^"]+)"')
LUA_NUM = {k: re.compile(k + r"\s*=\s*(\d+(?:\.\d+)?)") for k in ("minActivePlayers", "targetChancePerDay", "maxChecksPerDay", "initialChance")}
LUA_GAP = re.compile(r'minGapBetween\s*=\s*"([^"]+)"')
LUA_DAYS = re.compile(r"allowedDays\s*=\s*(\{[^}]*\}|\"\w+\")")
DAY_PT = {"Monday": "seg", "Tuesday": "ter", "Wednesday": "qua", "Thursday": "qui", "Friday": "sex", "Saturday": "sáb", "Sunday": "dom"}


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
            raid = _raid(r.get("name"), _title(file.split("/")[0]) if "/" in file else "", "xml", monsters, pos)
            raid["auto"] = {"margin": int(r.get("margin") or 0), "repeat": r.get("repeat", "") in ("yes", "true", "1")}
            out.append(raid)
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
        raid = _raid(m.group(1), _title(where), kind, monsters, area.groups() if area else None)
        cfg = text[m.end():m.end() + 600]
        days = LUA_DAYS.search(cfg)
        days = re.findall(r"\w+day", days.group(1)) if days else []
        gap = LUA_GAP.search(cfg)
        raid["auto"] = {k: float(rx.search(cfg).group(1)) if rx.search(cfg) else None for k, rx in LUA_NUM.items()}
        a = raid["auto"]
        lo, hi = _span(a)
        a["chance_text"] = (f"{_pct(lo)}%" if lo == hi else f"{_pct(lo)} a {_pct(hi)}%") if lo is not None else "sem chance"
        raid["auto"].update(days="todo dia" if len(days) in (0, 7) else ", ".join(DAY_PT.get(d, d) for d in days),
                            gap=gap.group(1) if gap else "")
        out.append(raid)
    # the same Lua raid can be registered by two files: keep the first
    seen, unique = set(), []
    for r in out:
        if r["name"] not in seen:
            seen.add(r["name"])
            unique.append(r)
    return sorted(unique, key=lambda r: (r["where"], r["label"]))


def _span(a):
    vals = sorted(v for v in (a["initialChance"], a["targetChancePerDay"]) if v is not None)
    return (vals[0], vals[-1]) if vals else (None, None)


def _pct(v):
    return f"{v:g}".replace(".", ",")


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


# ---------------------------------------------------------------- automatic raids
# Lua raids roll a chance every minute (data/libs/systems/raids.lua). The panel keeps overrides in
# `cockpit_raid_auto` and the bridge applies them (raid_auto): off, chance per day and minimum players.
# Legacy XML raids have no per-raid switch in the engine: only all on or all off (disableLegacyRaids).

# The old weekly schedule of raids_schedule.lua, with the raid names that really exist. It now lives in the Agenda.
WEEKLY = [
    ("Midnight Panther (terça)", "tiquanda.midnight-panther", "1", "16:00"),
    ("Draptor (quarta)", "farmine.draptor", "2", "12:00"),
    ("Undead Cavebear (quinta)", "farmine.undead-cavebear", "3", "19:00"),
    ("Draptor (sábado)", "farmine.draptor", "5", "20:00"),
    ("Orc Backpack (domingo)", "Orc Backpack", "6", "13:00"),
    ("Midnight Panther (domingo)", "tiquanda.midnight-panther", "6", "15:00"),
]


def seed_weekly(next_run):
    """Once: copy the game's weekly raid schedule into the Agenda (the game's own copy called names that do not exist)."""
    if db.one("SELECT 1 AS x FROM cockpit_settings WHERE k = 'raids.weekly_seeded'"):
        return
    for name, raid, day, at in WEEKLY:
        job = {"kind": "weekly", "at_time": at, "weekdays": day, "every_min": 0, "last_run": 0}
        db.run("INSERT INTO cockpit_schedules (name, action, text, kind, at_time, weekdays, created_by, next_run) "
               "VALUES (%s, 'start_raid', %s, 'weekly', %s, %s, 'cockpit', %s)", f"Raid: {name}", raid, at, day, next_run(job, int(time.time())))
    db.run("INSERT INTO cockpit_settings (k, v) VALUES ('raids.weekly_seeded', '1')")


def overrides():
    return {r["name"]: r for r in db.all("SELECT * FROM cockpit_raid_auto")}


def auto_rows():
    """Lua raids with their own settings and the panel's override."""
    over = overrides()
    kv = {}
    for r in db.all("SELECT key_name, timestamp DIV 1000 AS timestamp FROM kv_store WHERE key_name LIKE 'raids.%%.last-occurrence'"):
        kv[r["key_name"][6:-16]] = r["timestamp"]
    rows = []
    for r in all_raids():
        if r["kind"] == "xml":
            continue
        o = over.get(r["name"], {})
        rows.append(dict(r, enabled=o.get("enabled", 1) != 0, chance=o.get("chance"), min_players=o.get("min_players"),
                         last=kv.get(r["name"])))
    return rows


def legacy_rows():
    return [r for r in all_raids() if r["kind"] == "xml"]


def save_override(name, f):
    if not get(name) or get(name)["kind"] == "xml":
        return "Raid não encontrada."

    def num(key, lo, hi):
        try:
            return max(lo, min(hi, float(str(f.get(key, "")).strip().replace(",", "."))))
        except ValueError:
            return None

    db.run("INSERT INTO cockpit_raid_auto (name, enabled, chance, min_players) VALUES (%s, %s, %s, %s) "
           "ON DUPLICATE KEY UPDATE enabled = VALUES(enabled), chance = VALUES(chance), min_players = VALUES(min_players)",
           name, 1 if f.get("ligada") else 0, num("chance", 0, 100), None if num("min_players", 0, 500) is None else int(num("min_players", 0, 500)))
    return ""


def legacy_on():
    r = db.one("SELECT v FROM cockpit_settings WHERE k = 'world.disableLegacyRaids'")
    return not (r and r["v"] == "1")
