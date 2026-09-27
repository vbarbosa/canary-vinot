"""Dungeon do grupo: the ~50 existing boss-lever rooms (data/libs/functions/boss_lever.lua) already
in the otservbr-global map, with a panel screen on top instead of new map geometry.

Boss configs are read once from the scripts that register them (name, level, timers); nothing here
changes the map. Live state (who is inside, cooldowns) comes from the game via `cockpit_dungeon_status`,
written by the bridge every minute, and is overridden from the panel via `cockpit_dungeon_auto`.
"""

import glob
import os
import re

from . import db, places

CONFIG_RE = re.compile(
    r'boss\s*=\s*\{\s*name\s*=\s*"([^"]+)"(?:.*?position\s*=\s*Position\((\d+),\s*(\d+),\s*(\d+)\))?',
    re.DOTALL,
)
NUM_RE = {k: re.compile(k + r"\s*=\s*(\d+(?:\s*\*\s*\d+)*)") for k in ("requiredLevel", "timeToDefeat", "timeToFightAgain")}


def _num(text, key):
    m = NUM_RE[key].search(text)
    if not m:
        return None
    try:
        n = 1
        for part in m.group(1).split("*"):
            n *= int(part.strip())
        return n
    except ValueError:
        return None


def all_bosses():
    out = {}
    base = os.path.dirname(places.DATAPACK)
    for path in sorted(glob.glob(os.path.join(places.DATAPACK, "**", "*.lua"), recursive=True)):
        with open(path, encoding="utf-8", errors="replace") as f:
            text = f.read()
        if "BossLever(" not in text:
            continue
        starts = [m.start() for m in re.finditer(r"boss\s*=\s*\{", text)]
        for i, start in enumerate(starts):
            end = starts[i + 1] if i + 1 < len(starts) else len(text)
            block = text[start:end]
            m = CONFIG_RE.search(block)
            if not m:
                continue
            name = m.group(1)
            if name in out:
                continue
            x, y, z = (int(v) for v in m.group(2, 3, 4)) if m.group(2) else (None, None, None)
            out[name] = {
                "name": name, "x": x, "y": y, "z": z,
                "required_level": _num(block, "requiredLevel") or 0,
                "time_to_defeat": _num(block, "timeToDefeat"),
                "time_to_fight_again": _num(block, "timeToFightAgain"),
                "file": os.path.relpath(path, base),
            }
    return out


def overrides():
    return {r["name"]: r for r in db.all("SELECT * FROM cockpit_dungeon_auto")}


def status():
    return {r["name"]: r for r in db.all("SELECT * FROM cockpit_dungeon_status")}


def rows():
    over, stat = overrides(), status()
    out = []
    for name, b in sorted(all_bosses().items()):
        o = over.get(name, {})
        s = stat.get(name, {})
        out.append(dict(b, disabled=bool(o.get("disabled")),
                        time_to_defeat=o.get("time_to_defeat") or b["time_to_defeat"],
                        time_to_fight_again=o.get("time_to_fight_again") or b["time_to_fight_again"],
                        extra_item_id=o.get("extra_item_id"), extra_item_qty=o.get("extra_item_qty") or 1,
                        extra_chance=float(o["extra_chance"]) if o.get("extra_chance") is not None else 100,
                        players_inside=s.get("players_inside", 0), updated_at=s.get("updated_at")))
    return out


def get(name):
    return next((r for r in rows() if r["name"] == name), None)


def save_override(name, f):
    if name not in all_bosses():
        return "Dungeon não encontrada."

    def num(key, lo, hi):
        v = str(f.get(key, "")).strip()
        if not v:
            return None
        try:
            return max(lo, min(hi, float(v.replace(",", "."))))
        except ValueError:
            return None

    ttd, ttf = num("tempo_limite", 30, 7200), num("tempo_espera", 0, 30 * 24 * 3600)
    item_id, qty, chance = num("premio_item", 100, 99999), num("premio_qtd", 1, 1000), num("premio_chance", 0, 100)
    db.run(
        "INSERT INTO cockpit_dungeon_auto (name, disabled, time_to_defeat, time_to_fight_again, extra_item_id, extra_item_qty, extra_chance) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE disabled=VALUES(disabled), time_to_defeat=VALUES(time_to_defeat), "
        "time_to_fight_again=VALUES(time_to_fight_again), extra_item_id=VALUES(extra_item_id), extra_item_qty=VALUES(extra_item_qty), extra_chance=VALUES(extra_chance)",
        name, 1 if f.get("desativada") else 0, None if ttd is None else int(ttd), None if ttf is None else int(ttf),
        None if item_id is None else int(item_id), int(qty or 1), chance if chance is not None else 100,
    )
    return ""
