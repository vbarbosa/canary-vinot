"""Pedra Metin: a stone with a lot of life that players beat on. As it loses health it calls waves of
monsters; when it breaks, everyone who hit it rolls the loot table. The stone itself is a monster
("Metin Stone", `data-otservbr-global/monster/others/metin_stone.lua`) so the engine's own health bar,
damage and death events do the heavy lifting; the bridge (`metin_stone.lua` creaturescript) reads the
type's health/waves/loot straight from `cockpit_metin_types` at spawn time and keeps everything else
(damage per player, when it broke) in memory until death, then writes it here for the panel to show.

Waves and loot are one line of text each, not JSON (nothing else in this codebase parses JSON in Lua):
  waves: "75,Rotworm,5;50,Rotworm Queen,1;25,Rotworm,8"   -> at X% of life left, spawn N of a monster
  loot:  "3031,80,10,50;3035,40,1,5"                       -> item id, chance % per player, min, max
"""

import re
import time

from . import db

WAVE_RE = re.compile(r"^\s*(\d{1,3})\s*,\s*([^,]+?)\s*,\s*(\d{1,3})\s*$")
LOOT_RE = re.compile(r"^\s*(\d{1,6})\s*,\s*(\d{1,3})\s*,\s*(\d{1,4})\s*,\s*(\d{1,4})\s*$")
STATUS = {"alive": "Viva", "destroyed": "Destruída", "removed": "Removida pelo painel", "expired": "Servidor reiniciou"}


def parse_waves(text):
    """'75,Rotworm,5;...' -> [(at_pct, monster, amount)], or None if any line makes no sense."""
    out = []
    for part in [p for p in str(text).split(";") if p.strip()]:
        m = WAVE_RE.match(part)
        if not m or not 1 <= int(m.group(1)) <= 99 or not 1 <= int(m.group(3)) <= 200:
            return None
        out.append((int(m.group(1)), m.group(2).strip(), int(m.group(3))))
    out.sort(key=lambda w: -w[0])
    return out


def parse_loot(text):
    """'3031,80,10,50;...' -> [(item_id, chance_pct, min, max)], or None if any line makes no sense."""
    out = []
    for part in [p for p in str(text).split(";") if p.strip()]:
        m = LOOT_RE.match(part)
        if not m:
            return None
        item_id, chance, lo, hi = (int(g) for g in m.groups())
        if not 1 <= chance <= 100 or lo < 1 or hi < lo:
            return None
        out.append((item_id, chance, lo, hi))
    return out


def types():
    rows = db.all("SELECT * FROM cockpit_metin_types ORDER BY name")
    for r in rows:
        r["waves_n"], r["loot_n"] = len(parse_waves(r["waves"]) or []), len(parse_loot(r["loot"]) or [])
    return rows


def get_type(tid):
    return db.one("SELECT * FROM cockpit_metin_types WHERE id = %s", tid)


def save_type(f, tid=None):
    name = " ".join(str(f.get("name", "")).split())[:64]
    if not name:
        return "Dê um nome pra pedra."
    health = str(f.get("health", "")).strip()
    if not health.isdigit() or not 100 <= int(health) <= 1_000_000:
        return "Vida: de 100 a 1.000.000."
    waves = parse_waves(f.get("waves", ""))
    if waves is None:
        return "Ondas: uma por linha, \"% de vida,monstro,quantidade\" (ex.: 75,Rotworm,5)."
    loot = parse_loot(f.get("loot", ""))
    if loot is None:
        return "Loot: uma por linha, \"id do item,chance %,mínimo,máximo\" (ex.: 3031,80,10,50)."
    waves_text, loot_text = ";".join(f"{a},{m},{n}" for a, m, n in waves), ";".join(f"{i},{c},{lo},{hi}" for i, c, lo, hi in loot)
    if tid:
        db.run("UPDATE cockpit_metin_types SET name=%s, health=%s, waves=%s, loot=%s WHERE id=%s", name, health, waves_text, loot_text, tid)
    else:
        db.run("INSERT INTO cockpit_metin_types (name, health, waves, loot, created_at) VALUES (%s,%s,%s,%s,%s)",
               name, health, waves_text, loot_text, int(time.time()))
    return ""


def delete_type(tid):
    db.run("DELETE FROM cockpit_metin_types WHERE id = %s", tid)


def spots():
    return db.all("SELECT * FROM cockpit_metin_spots ORDER BY name")


def save_spot(f):
    name = " ".join(str(f.get("name", "")).split())[:64]
    if not name:
        return "Dê um nome pro lugar."
    try:
        x, y, z = int(f.get("x")), int(f.get("y")), int(f.get("z"))
    except (TypeError, ValueError):
        return "Coordenadas inválidas."
    if not 0 <= z <= 15:
        return "Andar (z) de 0 a 15."
    db.run("INSERT INTO cockpit_metin_spots (name, x, y, z) VALUES (%s,%s,%s,%s)", name, x, y, z)
    return ""


def delete_spot(sid):
    db.run("DELETE FROM cockpit_metin_spots WHERE id = %s", sid)


def active():
    return db.all("SELECT * FROM cockpit_metin_active WHERE status = 'alive' ORDER BY created_at DESC")


def history(limit=40):
    return db.all("SELECT * FROM cockpit_metin_active WHERE status <> 'alive' ORDER BY COALESCE(ended_at, created_at) DESC LIMIT %s", limit)


def damage_board(active_id):
    return db.all("SELECT * FROM cockpit_metin_damage WHERE active_id = %s ORDER BY damage DESC", active_id)


def spawn(actor, type_id, x, y, z):
    t = get_type(type_id)
    if not t:
        return None, "Escolha um tipo de pedra."
    aid = db.run(
        "INSERT INTO cockpit_metin_active (type_id, type_name, x, y, z, health_max, health_now, status, created_by, created_at) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,'alive',%s,%s)",
        type_id, t["name"], x, y, z, t["health"], t["health"], actor, int(time.time()),
    )
    db.enqueue(actor, "metin_spawn", arg1=type_id, arg2=x, arg3=y, arg4=z, text=str(aid))
    return aid, ""


def remove(actor, aid):
    a = db.one("SELECT * FROM cockpit_metin_active WHERE id = %s AND status = 'alive'", aid)
    if not a:
        return "Essa pedra já não está mais lá."
    db.enqueue(actor, "metin_remove", arg1=aid)
    return ""
