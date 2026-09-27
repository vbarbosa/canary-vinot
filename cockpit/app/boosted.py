"""Criatura e boss do dia (boosted): the game draws them when it starts, from `boosted_creature` and `boosted_boss`.

The engine keeps the row when its `date` is today's day of the month (server clock, UTC in the container), and draws a
new one otherwise. So the panel picks by writing the row with today's day: it counts from the next game start
(daily server save or a restart). "Fixar" makes the panel's minute loop rewrite the row every day, so the pick
survives the midnight turn.
"""

import glob
import os
import re
import time
from functools import lru_cache

from . import db, places

NAME = re.compile(r'Game\.createMonsterType\("([^"]+)"\)')
RACE = re.compile(r"monster\.raceId\s*=\s*(\d+)")
BOSS_RACE = re.compile(r"bossRaceId\s*=\s*(\d+)")
ARCHFOE = re.compile(r"bossRace\s*=\s*RARITY_ARCHFOE")
LOOK = {k: re.compile(k + r"\s*=\s*(\d+)") for k in ("lookType", "lookHead", "lookBody", "lookLegs", "lookFeet", "lookAddons", "lookMount")}
TABLES = {"creature": "boosted_creature", "boss": "boosted_boss"}


@lru_cache(maxsize=1)
def monsters():
    """(creatures, bosses): what the game can boost, with the outfit it shows."""
    creatures, bosses = {}, {}
    for path in glob.glob(os.path.join(places.DATAPACK, "monster", "**", "*.lua"), recursive=True):
        with open(path, encoding="utf-8", errors="replace") as f:
            text = f.read()
        name = NAME.search(text)
        if not name:
            continue
        look = {k: int(m.group(1)) if (m := rx.search(text)) else 0 for k, rx in LOOK.items()}
        race, boss = RACE.search(text), BOSS_RACE.search(text)
        if race and int(race.group(1)) > 0:
            creatures[name.group(1)] = {"name": name.group(1), "race": int(race.group(1)), **look}
        if boss and ARCHFOE.search(text):
            bosses[name.group(1)] = {"name": name.group(1), "race": int(boss.group(1)), **look}
    return dict(sorted(creatures.items())), dict(sorted(bosses.items()))


def today():
    return time.gmtime().tm_mday


def current(kind):
    return db.one(f"SELECT boostname, date, raceid FROM {TABLES[kind]} LIMIT 1")


def pinned(kind):
    r = db.one("SELECT v FROM cockpit_settings WHERE k = %s", f"boosted.{kind}")
    return r["v"] if r else ""


def choose(kind, name, pin):
    pool = monsters()[0 if kind == "creature" else 1]
    m = pool.get(name)
    if not m:
        return "Não achei esse nome na lista."
    _write(kind, m)
    db.run("INSERT INTO cockpit_settings (k, v) VALUES (%s, %s) ON DUPLICATE KEY UPDATE v = VALUES(v)", f"boosted.{kind}", name if pin else "")
    return ""


def draw(kind):
    """Let the game draw a new one at the next start."""
    db.run(f"UPDATE {TABLES[kind]} SET date = '0'")
    db.run("DELETE FROM cockpit_settings WHERE k = %s", f"boosted.{kind}")


def _write(kind, m):
    extra = "looktypeEx = 0, " if kind == "boss" else ""
    sql = (f"UPDATE {TABLES[kind]} SET date = %s, boostname = %s, raceid = %s, {extra}looktype = %s, lookhead = %s, lookbody = %s, "
           "looklegs = %s, lookfeet = %s, lookaddons = %s, lookmount = %s")
    args = (str(today()), m["name"], str(m["race"]), m["lookType"], m["lookHead"], m["lookBody"], m["lookLegs"], m["lookFeet"],
            m["lookAddons"], m["lookMount"])
    if not db.one(f"SELECT 1 AS x FROM {TABLES[kind]} LIMIT 1"):
        db.run(f"INSERT INTO {TABLES[kind]} (boostname, date, raceid) VALUES ('default', '0', '0')")
    db.run(sql, *args)


def tick():
    """Keep pinned picks dated today, so the next game start keeps them."""
    for kind in TABLES:
        name = pinned(kind)
        cur = current(kind)
        if name and cur and (cur["boostname"] != name or str(cur["date"]) != str(today())):
            m = monsters()[0 if kind == "creature" else 1].get(name)
            if m:
                _write(kind, m)
